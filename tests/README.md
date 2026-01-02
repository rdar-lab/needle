# Unit Tests for Needle

## Install Test Dependencies

```bash
# Using uv
uv pip install pytest pytest-cov pytest-asyncio
```

## Running Tests

```bash
# Run all tests
pytest

# Run tests with verbose output
pytest -v

# Run tests and generate coverage report
pytest --cov=app --cov-report=html --cov-report=term-missing

# Run specific test class
pytest tests/test_version_detection.py::TestVersionDetection

# Run specific test method
pytest tests/test_version_detection.py::TestVersionDetection::test_detect_java_8_no_smr

# Run tests and show print output
pytest -v -s
```

## Test Coverage

The current test suite includes **90+ test cases** covering the following aspects:

### 1. Version Detection (TestVersionDetection)
- Java 8/11/17/21/25 version identification
- SMR section detection
- Future version fallback handling

### 2. Parser Factory (TestCreateParser)
- Create correct parser instance based on content
- Automatic version detection and parser selection

### 3. Java 8 Parser (TestJava8Parser)
- Basic thread header parsing
- VM thread parsing
- Daemon thread identification

### 4. Java 11 Parser (TestJava11Parser)
- Thread header parsing with cpu/elapsed time
- GC thread parsing
- SMR section skipping

### 5. Java 21 Parser (TestJava21Parser)
- Decimal nid conversion
- Simplified format thread header parsing

### 6. Java 25 Parser (TestJava25Parser)
- Verify compatibility with Java 21 parser

### 7. State Mapping (TestStateMapping)
- All JVM internal states to standard states mapping
- Detailed state generation (various reasons for waiting/timed_waiting/runnable)

### 8. Thread Pool Detection (TestThreadPoolDetection)
- 13+ thread pool pattern recognition
- Suffix pattern handling
- Special thread identification

### 9. Prefix Detection (TestPrefixDetection)
- Timestamp prefix detection
- Line prefix stripping

### 10. Full Parsing Integration Tests (TestFullParsingIntegration)
- Complete thread dump parsing
- Stack trace extraction
- Detailed state analysis

### 11. Deadlock Parsing (TestDeadlockParsing)
- Simple deadlock detection
- Multiple deadlock detection

## Test File Structure

```
tests/
├── __init__.py
├── test_version_detection.py       # Version detection tests
├── test_parser_headers.py          # Parser-specific header parsing tests
├── test_state_and_pool.py          # State mapping and thread pool detection tests
├── test_parser_factory.py          # Parser factory and wrapper tests
├── test_parser_integration.py      # Integration tests for complete parsing
└── README.md                       # This file
```

## Code Coverage Goals

- Current target: **90%+**
- Core parser.py module should achieve higher coverage

## Next Steps

Consider adding more tests for the following modules:

1. `app/core/analyzer.py` - Analyzer tests
2. `app/core/stackcollapse_jstack.py` - Stack collapse tests
3. `app/core/flamegraph_pl.py` - Flamegraph generation tests
4. `app/api/upload.py` - API endpoint integration tests
