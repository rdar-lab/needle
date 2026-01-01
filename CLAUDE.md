# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Needle is a web application for analyzing Java thread dumps with interactive visualizations. It's built with Python/FastAPI backend and vanilla JavaScript frontend, providing flamegraph visualizations and comprehensive thread analysis.

## Common Commands

### Installation
```bash
# Using uv (recommended)
pip install uv
uv sync

# Or using pip
pip install -e .
```

### Running the Application
```bash
# Option 1: Using the provided script
./start_server.sh

# Option 2: Direct Python execution (includes auto-reload)
python -m app.main

# Option 3: Using uvicorn directly
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The application runs on http://localhost:8000

### Testing
```bash
# Upload example thread dump files via web UI or API
curl -X POST "http://localhost:8000/api/upload" \
  -F "file=@examples/java21_jstack.txt"
```

Example files are in the `examples/` directory for testing various Java versions (8, 17, 21) and scenarios (deadlocks).

## Architecture

### Core Components

**app/core/parser.py**: Thread dump parser
- Supports Java 8, 11, 17, 21, 25 formats
- Handles both standard jstack output and timestamp-prefixed dumps
- Returns structured ThreadInfo objects with state, stack trace, and metadata
- Uses strategy pattern with version-specific parsers (Java8Parser, Java11Parser, Java21Parser, Java25Parser)
- Automatic Java version detection via SMR section and version string matching
- Maps JVM internal thread states to standard Thread.State values
- Comprehensive thread pool detection from thread names and stack traces

**app/core/analyzer.py**: Thread data analyzer
- Generates thread statistics and state distributions (basic and detailed)
- Detects thread pools and groups with state breakdown
- Identifies blocked/waiting threads
- Analyzes CPU consumption
- Advanced deadlock detection beyond JVM reports (via lock dependency analysis)
- GC thread counting (G1, Parallel, CMS, ZGC, Shenandoah)

**app/core/stackcollapse_jstack.py**: Stack trace collapser for flamegraph generation
- Similar to Brendan Gregg's stackcollapse.pl
- Collapses stack traces into format suitable for flamegraph visualization

**app/core/flamegraph_generator.py**: Main interface for flamegraph generation
- Orchestrates multiple rendering implementations
- Provides graceful fallback between implementations

**app/core/flamegraph_pl.py**: Primary Perl-style flamegraph implementation in Python
- Generates SVG flamegraphs with Java-specific color schemes
- Supports inverted (icicle) graph format
- Implements flamegraph.pl's flow algorithm for stack merging
- Interactive features: zoom, search, mouseover tooltips

**app/core/flamegraph_js.py**: JavaScript code embedded in SVG
- Provides interactivity for flamegraph (zoom, search, state management)
- Embedded into generated SVG by flamegraph_pl.py

### API Layer

**app/api/upload.py**: Single POST endpoint for thread dump analysis
- Accepts multipart file uploads (max 100MB, .log and .txt files)
- Handles multiple encodings (UTF-8 primary, Latin-1 fallback)
- Returns complete analysis with statistics, deadlocks, flamegraph SVG and data
- Includes potential deadlock detection (beyond JVM-reported deadlocks)
- Generates simplified flamegraph data for frontend rendering

### Data Models

**app/models/thread_data.py**: Pydantic v2 models for type safety
- ThreadInfo: Individual thread data with raw_state and detailed_state support
- DeadlockInfo: Deadlock information
- ThreadStatistics: Aggregated statistics including gc_threads and detailed_state_distribution
- AnalysisResult: Complete API response structure

### Frontend

**app/static/**: Single-page application (no build step required)
- index.html: Main UI
- css/style.css: Responsive styling
- js/app.js: Frontend logic with Chart.js visualizations and interactive flamegraph rendering

## Key Implementation Details

### Flamegraph Generation
The application supports multiple flamegraph rendering backends with graceful fallback:
1. Primary: Perl-style algorithm in Python (`flamegraph_pl.py`)
2. Secondary: JavaScript-based rendering (`flamegraph_js.py`)
Both generate SVG output with Java-specific warm color scheme (red/orange/yellow for hot methods).

### Thread Dump Format Support
The parser uses flexible regex patterns to handle:
- Standard jstack output: `"Thread-Name" #123 prio=5 ...`
- Thread state format: `"Thread-Name" #123 [0x...] java.lang.Thread.State: RUNNABLE`
- Timestamp-prefixed: `2024-01-01T10:30:45.123+0000 [1] "Thread-Name" ...`
- Java versions: 8, 11, 17, 21, 25

### Thread State Analysis
States tracked: RUNNABLE, BLOCKED, WAITING, TIMED_WAITING
- Basic state distribution and detailed state with reasons (e.g., "WAITING (Parking)", "RUNNABLE (Socket I/O)")
- Deadlock detection from JVM-reported deadlocks
- Advanced potential deadlock detection via lock dependency graph analysis
- Thread pool detection by common name patterns with state breakdown
- CPU time analysis from thread dump headers
- GC thread identification and counting
- Daemon vs non-daemon thread counting

## Code Quality Assessment

### Strengths

**Architecture & Design**
- Clean modular architecture with clear separation of concerns
- Strategy pattern for version-specific parsers (Java8/11/21/25)
- Good use of Pydantic v2 for type safety and validation
- Graceful fallback mechanisms (flamegraph generation, encoding detection)

**Robustness**
- Comprehensive error handling with fallback encoding support
- Automatic Java version detection
- Support for multiple thread dump formats and edge cases
- JVM internal thread state mapping for compatibility

**Features**
- Advanced deadlock detection beyond JVM reports (lock dependency analysis)
- Detailed state analysis with reason categorization
- Comprehensive thread pool detection (15+ pool patterns)
- GC thread identification across different GC algorithms

**Code Organization**
- Well-structured with consistent naming conventions
- Good use of type hints throughout
- Clear method responsibilities

### Areas for Improvement

**Debug Code Cleanup** (app/api/upload.py:65-112)
- Remove or replace `print()` statements with proper logging
- Debug prints should use `logging` module with appropriate levels

**Code Duplication** (app/core/parser.py:194-286)
- `_map_raw_state_to_standard()` and `_format_raw_state()` have similar logic
- Consider consolidating state mapping functions

**Long Methods** (app/core/parser.py:336-391)
- `_detect_pool_from_name()` is 55+ lines with many patterns
- Consider extracting patterns to a configuration dict or constants

**Regex Performance** (app/core/analyzer.py:164-168)
- Regex patterns in `detect_potential_deadlocks()` are compiled on every call
- Move pattern compilation to class/module level for better performance

**Magic Numbers**
- File size limit (100MB) hardcoded in upload.py:40
- Frame height (16), font size (12), etc. hardcoded in flamegraph_pl.py
- Consider extracting to configuration

**Method Length** (app/core/parser.py:113-192)
- `_parse_thread()` method is 80 lines
- Consider breaking into smaller methods for better testability

**Missing Error Handling**
- Some parsing failures return empty data rather than raising exceptions
- Consider more explicit error reporting for invalid input formats

## Development Notes

- Python version: 3.11+ (project currently uses 3.14)
- Server: Uvicorn with auto-reload in development
- Max file upload: 100MB
- No frontend build step - vanilla JS with direct browser execution
- Chart.js 4.4 for client-side charts (thread state distribution pie chart, etc.)
- Static files served from `app/static/` by FastAPI

## Adding Features

- **New analyzers**: Add to `app/core/`, follow existing patterns in `analyzer.py`
- **New API endpoints**: Add to `app/api/`, follow upload.py patterns
- **Data models**: Extend Pydantic models in `app/models/thread_data.py`
- **Frontend changes**: Update files in `app/static/` - no build required
- **New thread dump formats**: Extend parser patterns in `app/core/parser.py`