"""API endpoints for thread dump analysis."""

import uuid
from pathlib import Path
from typing import Dict

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse

from app.core.analyzer import ThreadAnalyzer
from app.core.flamegraph_generator import generate_flamegraph_svg_from_content
from app.core.flamegraph_pl import generate_flamegraph_from_collapsed
from app.core.parser import ThreadDumpParser, extract_java_version_string, extract_timestamp
from app.core.stackcollapse_jstack import collapse_jstack, collapse_threads
from app.models.thread_data import AnalysisResult

router = APIRouter(prefix="/api", tags=["analysis"])


@router.post("/upload")
async def upload_thread_dump(file: UploadFile = File(...)):
    """
    Upload and analyze a Java thread dump file.

    Args:
        file: Uploaded thread dump file

    Returns:
        Analysis result with thread statistics and flamegraph data
    """
    # Validate file type
    if not file.filename or (not file.filename.endswith('.log') and
                             not file.filename.endswith('.txt')):
        raise HTTPException(
            status_code=400,
            detail="Invalid file format. Please upload a .log or .txt file."
        )

    # Check file size (limit to 100MB)
    MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB
    content = await file.read()

    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size is {MAX_FILE_SIZE // (1024*1024)}MB"
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
                detail=f"Failed to decode file: {str(e)}"
            )

    # Parse thread dump
    parser = ThreadDumpParser()
    try:
        threads, deadlocks = parser.parse(thread_dump_content)
        print(f"[DEBUG] Parsed {len(threads)} threads, {len(deadlocks)} deadlocks")
        if len(threads) == 0:
            print("[DEBUG] No threads found! First 500 chars of content:")
            print(thread_dump_content[:500])
    except Exception as e:
        print(f"[ERROR] Parsing failed: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to parse thread dump: {str(e)}"
        )

    # Analyze threads
    # Extract Java version string and timestamp
    java_version = extract_java_version_string(thread_dump_content)
    timestamp = extract_timestamp(thread_dump_content)
    analyzer = ThreadAnalyzer(threads, java_version=java_version, timestamp=timestamp)
    statistics = analyzer.analyze()

    # Detect potential deadlocks (beyond what JVM reports)
    # Pass JVM-reported deadlocks to avoid duplicates
    jvm_deadlock_threads = set()
    for dl in deadlocks:
        jvm_deadlock_threads.add(tuple(sorted(dl.threads)))

    potential_deadlocks = analyzer.detect_potential_deadlocks(jvm_deadlock_threads)
    if potential_deadlocks:
        print(f"[INFO] Detected {len(potential_deadlocks)} potential deadlock(s)")

    # Generate flamegraph using perl scripts
    # Generate a unique session ID for this upload
    session_id = str(uuid.uuid4())[:8]

    # Also collapse stacks for data analysis
    collapsed = collapse_jstack(thread_dump_content, include_thread_name=False)

    flamegraph_url = None
    try:
        # Generate SVG content directly (no file saved)
        flamegraph_svg = generate_flamegraph_svg_from_content(thread_dump_content)

        print(f"[INFO] Generated flamegraph SVG in memory")

    except Exception as e:
        print(f"[ERROR] Failed to generate flamegraph with perl scripts: {str(e)}")
        import traceback
        traceback.print_exc()

        # Fallback to Python implementation
        print("[INFO] Falling back to Python implementation...")
        collapsed_lines = [f"{stack} {count}" for stack, count in collapsed.items()]
        flamegraph_svg = generate_flamegraph_from_collapsed(
            collapsed_lines,
            title="Thread Dump Flame Graph",
            colors="java",
            countname="threads",
            nametype="Function:",
            inverted=True,
        )

    # Generate simplified data for frontend
    flamegraph_data = []
    for stack, count in sorted(collapsed.items(), key=lambda x: x[1], reverse=True):
        frames = stack.split(";")
        flamegraph_data.append({
            "frames": frames,
            "count": count,
            "depth": len(frames)
        })

    # Prepare response
    total_deadlocks = len(deadlocks) + len(potential_deadlocks)
    response_data = {
        "session_id": session_id,
        "statistics": statistics.model_dump(),
        "deadlocks": [d.model_dump() for d in deadlocks],
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