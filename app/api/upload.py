"""API endpoints for thread dump analysis."""

import logging
import uuid

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from typing import List

logger = logging.getLogger(__name__)

from app.core.analyzer import ThreadAnalyzer
from app.core.flamegraph_generator import generate_flamegraph_svg_from_content
from app.core.flamegraph_pl import generate_flamegraph_from_collapsed
from app.core.parser import ThreadDumpParser, extract_java_version_string, extract_timestamp
from app.core.stackcollapse_jstack import collapse_jstack

router = APIRouter(prefix="/api", tags=["analysis"])

# Configuration constants
MAX_FILE_SIZE_MB = 100
MAX_FILE_SIZE = MAX_FILE_SIZE_MB * 1024 * 1024  # 100MB
ALLOWED_FILE_EXTENSIONS = ['.log', '.txt']


@router.post("/upload")
async def upload_thread_dump(files: List[UploadFile] = File(...)):
    """
    Upload and analyze one or more Java thread dump files (burst).

    Args:
        files: List of uploaded thread dump files (single or multiple)

    Returns:
        Analysis result with thread statistics and flamegraph data merged from all files
    """
    # Validate and read all files
    if not files or len(files) == 0:
        raise HTTPException(
            status_code=400,
            detail="No files uploaded"
        )
    
    file_names = []
    thread_dump_contents = []
    
    for file in files:
        # Validate file type
        if not file.filename or not any(file.filename.endswith(ext) for ext in ALLOWED_FILE_EXTENSIONS):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file format for '{file.filename}'. Please upload {', '.join(ALLOWED_FILE_EXTENSIONS)} files."
            )
        
        file_names.append(file.filename)
        
        # Check file size
        content = await file.read()
        
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"File '{file.filename}' too large. Maximum size is {MAX_FILE_SIZE_MB}MB"
            )
        
        # Decode content
        try:
            thread_dump_content = content.decode('utf-8')
        except UnicodeDecodeError:
            try:
                thread_dump_content = content.decode('latin-1')
            except Exception as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"Failed to decode file '{file.filename}': {str(e)}"
                )
        
        thread_dump_contents.append(thread_dump_content)
    
    # Parse all thread dumps and collect threads
    parser = ThreadDumpParser()
    all_threads = []
    all_deadlocks = []
    java_versions = []
    timestamps = []
    
    for i, content in enumerate(thread_dump_contents):
        try:
            threads, deadlocks = parser.parse(content)
            logger.debug(f"Parsed {len(threads)} threads from file {i+1}/{len(thread_dump_contents)}")
            all_threads.extend(threads)
            all_deadlocks.extend(deadlocks)
            
            # Extract metadata from each dump
            java_version = extract_java_version_string(content)
            if java_version and java_version not in java_versions:
                java_versions.append(java_version)
            
            timestamp = extract_timestamp(content)
            if timestamp and timestamp not in timestamps:
                timestamps.append(timestamp)
                
        except Exception as e:
            logger.error(f"Parsing failed for file {i+1}: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Failed to parse thread dump from file {i+1} ('{file_names[i]}'): {str(e)}"
            )

    
    logger.info(f"Analyzing {len(all_threads)} threads from {len(files)} file(s)")
    
    # Use the first Java version and timestamp found (or combine them)
    combined_java_version = java_versions[0] if java_versions else None
    combined_timestamp = timestamps[0] if len(timestamps) == 1 else (
        f"{timestamps[0]} ... {timestamps[-1]}" if len(timestamps) > 1 else None
    )
    
    # Analyze threads
    analyzer = ThreadAnalyzer(all_threads, java_version=combined_java_version, timestamp=combined_timestamp)
    statistics = analyzer.analyze()

    # Detect potential deadlocks (beyond what JVM reports)
    # Pass JVM-reported deadlocks to avoid duplicates
    jvm_deadlock_threads = set()
    for dl in all_deadlocks:
        jvm_deadlock_threads.add(tuple(sorted(dl.threads)))

    potential_deadlocks = analyzer.detect_potential_deadlocks(jvm_deadlock_threads)
    if potential_deadlocks:
        logger.info(f"Detected {len(potential_deadlocks)} potential deadlock(s)")

    # Generate flamegraph using perl scripts
    # Generate a unique session ID for this upload
    session_id = str(uuid.uuid4())[:8]

    # Merge all collapsed stacks from all thread dumps
    merged_collapsed = {}
    for content in thread_dump_contents:
        collapsed = collapse_jstack(content, include_thread_name=False)
        for stack, count in collapsed.items():
            merged_collapsed[stack] = merged_collapsed.get(stack, 0) + count

    flamegraph_url = None
    try:
        # Generate SVG content directly using merged content
        # Concatenate all thread dump contents
        merged_content = "\n\n".join(thread_dump_contents)
        flamegraph_svg = generate_flamegraph_svg_from_content(merged_content)

        logger.info("Generated flamegraph SVG in memory from merged content")

    except Exception as e:
        logger.warning(f"Failed to generate flamegraph with primary implementation: {str(e)}", exc_info=True)

        # Fallback to Python implementation
        logger.info("Falling back to Python implementation...")
        collapsed_lines = [f"{stack} {count}" for stack, count in merged_collapsed.items()]
        flamegraph_svg = generate_flamegraph_from_collapsed(
            collapsed_lines,
            title="Thread Dump Flame Graph (Burst)",
            colors="java",
            countname="threads",
            nametype="Function:",
            inverted=True,
        )

    # Generate simplified data for frontend
    flamegraph_data = []
    for stack, count in sorted(merged_collapsed.items(), key=lambda x: x[1], reverse=True):
        frames = stack.split(";")
        flamegraph_data.append({
            "frames": frames,
            "count": count,
            "depth": len(frames)
        })

    # Prepare response
    total_deadlocks = len(all_deadlocks) + len(potential_deadlocks)
    response_data = {
        "session_id": session_id,
        "file_count": len(files),
        "file_names": file_names,
        "statistics": statistics.model_dump(),
        "deadlocks": [d.model_dump() for d in all_deadlocks],
        "potential_deadlocks": potential_deadlocks,  # Add detected potential deadlocks
        "total_deadlocks": total_deadlocks,  # Total count including potential deadlocks
        "flamegraph_svg": flamegraph_svg,
        "flamegraph_url": flamegraph_url,  # URL to the SVG file
        "flamegraph_data": flamegraph_data,
        "blocked_threads": len(analyzer.get_blocked_threads()),
        "waiting_threads": len(analyzer.get_waiting_threads()),
        "top_cpu_threads": [
            {
                "name": t.name,
                "state": t.state,
                "cpu_time": t.cpu_time,
                "stack_trace": t.stack_trace[:10]  # First 10 frames
            }
            for t in analyzer.get_top_cpu_threads(10)
        ]
    }

    return JSONResponse(content=response_data)