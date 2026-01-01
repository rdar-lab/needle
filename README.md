# Needle - Java Thread Dump Analyzer

<img src="./app/static/needle.jpg" alt="Needle" width="10%">

Yet another modern web application for analyzing Java thread dumps with interactive visualizations.

## Features

- **Thread Statistics**: View comprehensive thread counts and state distributions
- **State Analysis**: Visual breakdown of RUNNABLE, BLOCKED, WAITING, and TIMED_WAITING threads
- **Thread Pool Detection**: Identify and analyze thread pools
- **Deadlock Detection**: Automatic detection and reporting of deadlocks
- **Interactive Flamegraph**: SVG-based flamegraph visualization of stack traces with multiple rendering backends
- **Top CPU Consumers**: Identify threads consuming the most CPU time
- **Modern Web UI**: Clean, responsive interface built with vanilla JavaScript and Chart.js
- **Multi-Version Support**: Supports Java 8, 11, 17, 21, and 25 thread dump formats with timestamps

## Quick Start

### Prerequisites

- Python 3.11 or higher

### Installation

1. Clone the repository:
```bash
cd needle
```

2. Install dependencies using uv (recommended):
```bash
pip install uv
uv sync
```

Or using pip:
```bash
pip install -e .
```

### Running the Application

Option 1: Using the start script (Linux/Mac):
```bash
chmod +x start_server.sh
./start_server.sh
```

Option 2: Manual start:
```bash
python -m app.main
```

The application will be available at: http://localhost:8000

## Usage

1. Open your browser and navigate to http://localhost:8000
2. Upload a Java thread dump file (.log or .txt format)
3. View the analysis results:
   - Thread statistics and state distribution
   - Thread pool information
   - Flamegraph visualization
   - Deadlock detection
   - Top CPU consuming threads

## Project Structure

```
needle/
├── app/
│   ├── api/
│   │   └── upload.py                # API endpoints for file upload and analysis
│   ├── core/
│   │   ├── parser.py                # Thread dump parser (supports Java 8/11/17/21/25 formats)
│   │   ├── analyzer.py              # Thread data analyzer
│   │   ├── stackcollapse_jstack.py  # Stack trace collapser for flamegraph
│   │   ├── flamegraph_generator.py  # Flamegraph SVG generator (main interface)
│   │   ├── flamegraph_pl.py         # Perl-style flamegraph implementation in Python
│   │   └── flamegraph_js.py         # JavaScript flamegraph implementation
│   ├── models/
│   │   └── thread_data.py           # Pydantic data models
│   ├── static/
│   │   ├── index.html               # Frontend UI
│   │   ├── css/
│   │   │   └── style.css            # Styles
│   │   └── js/
│   │       └── app.js               # Frontend logic with Chart.js
│   └── main.py                      # FastAPI application
├── examples/                         # Example thread dump files (Java 8/11/17/21/25)
├── pyproject.toml                   # Project dependencies
├── start_server.sh                  # Server startup script
└── README.md
```

## API Endpoints

### POST /api/upload
Upload and analyze a thread dump file.

**Request:**
- Method: POST
- Content-Type: multipart/form-data
- Body: file (thread dump file)

**Response:**
```json
{
  "session_id": "filename.log",
  "statistics": {
    "total_threads": 156,
    "state_distribution": {...},
    "thread_pools": {...},
    "thread_groups": {...}
  },
  "deadlocks": [...],
  "flamegraph_svg": "...",
  "flamegraph_data": [...],
  "blocked_threads": 10,
  "waiting_threads": 60,
  "top_cpu_threads": [...]
}
```

### GET /health
Health check endpoint for monitoring service availability.

## Technology Stack

### Backend
- **FastAPI**: Modern, fast web framework for building APIs
- **Pydantic v2**: Data validation using Python type annotations
- **Python 3.11+**: Latest Python features and performance improvements

### Frontend
- **Vanilla JavaScript**: No build step required
- **Chart.js 4.4**: Beautiful, responsive charts for data visualization
- **Custom SVG**: Interactive flamegraph visualization with multiple rendering backends

### Flamegraph Generation
The application supports multiple flamegraph rendering implementations:
- **Primary**: Perl-style implementation in Python (`flamegraph_pl.py`)
- **JavaScript**: Alternative rendering engine (`flamegraph_js.py`)
- **Fallback**: Graceful degradation between implementations

The flamegraph algorithm and visualization technique are based on [Brendan Gregg's FlameGraph project](https://github.com/brendangregg/FlameGraph), the industry-standard tool for flamegraph visualization.

## Architecture

### Core Components

- **app/core/parser.py**: Parses Java thread dump format into structured data
  - Supports standard Java thread dumps (jstack output)
  - Handles timestamp-prefixed formats (Java 8/11/17/21/25)
  - Flexible pattern matching for various thread dump styles
  - Automatic Java version detection via SMR section
  - JVM internal thread state mapping

- **app/core/analyzer.py**: Analyzes parsed thread data for statistics
  - Thread state distribution (basic and detailed with reasons)
  - Thread pool detection and grouping with state breakdown
  - Blocked and waiting thread identification
  - CPU time analysis
  - Advanced deadlock detection via lock dependency graph
  - GC thread counting (G1, Parallel, CMS, ZGC, Shenandoah)

- **app/core/stackcollapse_jstack.py**: Collapses stack traces for flamegraph generation
  - Similar to Brendan Gregg's stackcollapse.pl
  - Handles Java-specific stack trace formats

- **app/core/flamegraph_*.py**: Multiple flamegraph SVG generation implementations
  - Interactive visualization of stack traces
  - Configurable color schemes (Java-specific colors)
  - Inverted (icicle) graph format for better readability

- **app/api/upload.py**: API endpoints handling file uploads
  - File size validation (100MB limit)
  - Multiple encoding support (UTF-8, Latin-1)
  - Graceful error handling with fallback implementations

## Development

### Running in Development Mode

The application includes auto-reload when started with:
```bash
python -m app.main
```

Or using uvicorn directly:
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Adding Features

The codebase is organized for easy extension:
- Add new analyzers in `app/core/`
- Create new API endpoints in `app/api/`
- Extend data models in `app/models/`
- Update frontend in `app/static/`

## Supported Thread Dump Formats

The parser supports various Java thread dump formats:

1. **Standard jstack output** (Java 8, 11, 17, 21, 25)
2. **Timestamp-prefixed dumps** (from GC logs or monitoring tools)
3. **Minimal format** (thread name with basic info)

Example formats supported:
```
"Thread-Name" #123 prio=5 os_prio=31 cpu=12.34ms elapsed=234.56s tid=0x... nid=0x... runnable
"Thread-Name" #123 [0x...] java.lang.Thread.State: RUNNABLE
2024-01-01T10:30:45.123+0000 [1] "Thread-Name" prio=5 ...
```

## Limitations

- Maximum file size: 100MB
- Supported formats: .log, .txt
- Standard Java thread dump format (jstack output)
- Flamegraph generation may take longer for very large dumps (>1000 threads)