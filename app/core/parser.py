"""Java thread dump parser with version-specific implementations."""

import re
from abc import ABC, abstractmethod
from typing import List, Optional, Tuple
from app.models.thread_data import ThreadInfo, DeadlockInfo


class BaseThreadDumpParser(ABC):
    """Base class for version-specific thread dump parsers."""

    def __init__(self):
        self.threads: List[ThreadInfo] = []
        self.deadlocks: List[DeadlockInfo] = []
        self.raw_lines: List[str] = []
        self.prefix_skip: int = 0  # Number of characters to skip at start of each line (for timestamp/prefix)

    @abstractmethod
    def get_thread_header_pattern(self) -> re.Pattern:
        """Return regex pattern for thread header specific to this Java version."""
        pass

    @abstractmethod
    def parse_thread_header(self, line: str) -> Optional[dict]:
        """Parse thread header line and extract thread metadata."""
        pass

    @abstractmethod
    def skip_smr_section(self, lines: List[str], start_idx: int) -> int:
        """Skip SMR section if present, return new index."""
        pass

    def _detect_prefix_skip(self, content: str) -> int:
        """Detect number of characters to skip at start of each line.

        Finds the line containing 'Full thread dump' and calculates
        how many characters precede it (for timestamp/prefix patterns).

        Returns 0 if no prefix is detected.
        """
        lines = content.split('\n')
        for line in lines:
            # Look for "Full thread dump" (works for both Java HotSpot and OpenJDK)
            if 'Full thread dump' in line:
                idx = line.find('Full thread dump')
                if idx > 0:
                    # Found prefix - return its length
                    return idx
        return 0

    def _find_thread_dump_start(self, lines: List[str]) -> int:
        """Find the line where thread dump actually starts.

        Skips any leading log lines before the actual thread dump.
        Returns the index of the line containing 'Full thread dump'.
        """
        for i, line in enumerate(lines):
            stripped = self._strip_line_prefix(line)
            if 'Full thread dump' in stripped:
                return i
        return 0

    def _strip_line_prefix(self, line: str) -> str:
        """Strip detected prefix from a line."""
        if self.prefix_skip > 0 and len(line) > self.prefix_skip:
            return line[self.prefix_skip:]
        return line

    def parse(self, content: str) -> Tuple[List[ThreadInfo], List[DeadlockInfo]]:
        """Parse thread dump content."""
        self.threads = []
        self.deadlocks = []

        # Detect and store prefix skip length
        self.prefix_skip = self._detect_prefix_skip(content)

        self.raw_lines = content.split('\n')

        # Find where the actual thread dump starts (skip leading log lines)
        i = self._find_thread_dump_start(self.raw_lines)

        # Skip SMR section if present
        i = self.skip_smr_section(self.raw_lines, i)

        while i < len(self.raw_lines):
            line = self._strip_line_prefix(self.raw_lines[i])

            # Stop at end of thread dump section
            # These sections appear after all threads in a full thread dump
            stripped = line.strip()
            if (stripped.startswith('JNI global') or
                stripped.startswith('Heap') or
                stripped.startswith('Symbolic links') or
                stripped.startswith('ClassLoader')):
                break

            # Check for deadlock section
            if "Found one Java-level deadlock" in stripped or "Found a total of" in stripped:
                i = self._parse_deadlock(i)
                continue

            # Check for thread header
            thread_data = self.parse_thread_header(stripped)
            if thread_data:
                thread_info = self._parse_thread(thread_data, i)
                if thread_info:
                    self.threads.append(thread_info)

            i += 1

        return self.threads, self.deadlocks

    def _parse_thread(self, header_data: dict, line_idx: int) -> Optional[ThreadInfo]:
        """Parse a single thread from its header and stack trace."""
        name = header_data.get('name')
        if not name:
            return None

        # Parse state from next lines
        state = "UNKNOWN"
        raw_state = None  # Store raw state from header for JVM internal threads
        stack_trace = []
        thread_group = None
        pool_name = None

        # Look for thread state in next few lines
        for j in range(line_idx + 1, min(line_idx + 5, len(self.raw_lines))):
            stripped_line = self._strip_line_prefix(self.raw_lines[j])
            state_match = re.search(r'java\.lang\.Thread\.State:\s+(\S+(?:\s+\([^)]+\))?)', stripped_line)
            if state_match:
                full_state = state_match.group(1)
                state = full_state.split('(')[0].strip()
                break

        # If no state found, try to extract from thread header line (for JVM internal threads)
        if state == "UNKNOWN" and 'state_in_header' in header_data:
            raw_state = header_data['state_in_header'].strip()
            state = self._map_raw_state_to_standard(raw_state)

        # Extract stack trace
        j = line_idx + 1
        while j < len(self.raw_lines):
            line = self._strip_line_prefix(self.raw_lines[j]).strip()

            # Stop at empty line or next thread header
            if not line or line.startswith('"'):
                break

            # Parse stack frame
            if line.startswith('at '):
                frame = line[3:].strip()
                stack_trace.append(frame)

                # Detect thread pool from stack trace
                if not pool_name:
                    if "ThreadPoolExecutor" in frame or "ForkJoinPool" in frame:
                        pool_match = re.search(r'pool-\d+-\w+|ForkJoinPool\.\d+', frame)
                        if pool_match:
                            pool_name = pool_match.group(0)
            # Also include lock information lines
            elif line.startswith('- '):
                stack_trace.append(line)

            j += 1

        # Detect thread group from thread name
        if "/" in name:
            parts = name.split("/")
            thread_group = parts[0] if len(parts) > 1 else None

        # Calculate detailed state
        detailed_state = self._get_detailed_state(state, stack_trace, raw_state)

        # Extract pool name from thread name pattern
        if not pool_name:
            pool_name = self._detect_pool_from_name(name)

        return ThreadInfo(
            name=name,
            tid=header_data.get('tid'),
            nid=header_data.get('nid'),
            priority=header_data.get('priority', 0),
            state=state,
            raw_state=raw_state,  # Preserve raw state for JVM internal threads
            detailed_state=detailed_state,
            cpu_time=header_data.get('cpu_time'),
            elapsed_time=header_data.get('elapsed_time'),
            stack_trace=stack_trace,
            thread_group=thread_group,
            pool_name=pool_name,
            is_daemon=header_data.get('is_daemon', False)
        )

    def _map_raw_state_to_standard(self, raw_state: str) -> str:
        """Map raw thread state from header to standard state.

        Handles JVM internal thread states:
        - allocated -> RUNNABLE
        - initialized -> RUNNABLE
        - runnable -> RUNNABLE
        - waiting for monitor entry -> BLOCKED
        - waiting on condition -> WAITING
        - in Object.wait() -> WAITING
        - at breakpoint -> RUNNABLE
        - sleeping -> TIMED_WAITING
        - zombie -> UNKNOWN
        - unknown state -> UNKNOWN
        """
        # Remove trailing punctuation and normalize
        state_lower = raw_state.lower().strip().rstrip('.')

        # Map states to standard Thread.State values
        state_mapping = {
            'allocated': 'RUNNABLE',
            'initialized': 'RUNNABLE',
            'runnable': 'RUNNABLE',
            'in runnable': 'RUNNABLE',
            'waiting for monitor entry': 'BLOCKED',
            'waiting on condition': 'WAITING',
            'in object.wait()': 'WAITING',
            'at breakpoint': 'RUNNABLE',
            'sleeping': 'TIMED_WAITING',
            'zombie': 'UNKNOWN',
            'unknown state': 'UNKNOWN',
        }

        # Try exact match first
        if state_lower in state_mapping:
            return state_mapping[state_lower]

        # Try partial match for flexibility
        if 'runnable' in state_lower:
            return 'RUNNABLE'
        elif 'waiting for monitor' in state_lower or 'waiting to lock' in state_lower:
            return 'BLOCKED'
        elif 'waiting on condition' in state_lower:
            return 'WAITING'
        elif 'object.wait' in state_lower:
            return 'WAITING'
        elif 'sleep' in state_lower:
            return 'TIMED_WAITING'
        elif 'breakpoint' in state_lower:
            return 'RUNNABLE'
        elif 'zombie' in state_lower:
            return 'UNKNOWN'

        return 'UNKNOWN'

    def _format_raw_state(self, raw_state: str) -> str:
        """Format raw state to match frontend color mapping.

        Maps JVM internal thread states to consistent display format:
        - runnable -> Runnable
        - waiting on condition -> Waiting on condition
        - in Object.wait() -> In Object.wait()
        - waiting for monitor entry -> Waiting for monitor entry
        - sleeping -> Sleeping
        - allocated -> Allocated
        - initialized -> Initialized
        - at breakpoint -> At breakpoint
        - zombie -> Zombie
        - unknown state -> Unknown state
        """
        # Remove trailing punctuation and normalize
        state_lower = raw_state.lower().strip().rstrip('.')

        # Map to frontend display format
        state_display_map = {
            'runnable': 'Runnable',
            'in runnable': 'Runnable',
            'waiting on condition': 'Waiting on condition',
            'in object.wait()': 'In Object.wait()',
            'waiting for monitor entry': 'Waiting for monitor entry',
            'sleeping': 'Sleeping',
            'allocated': 'Allocated',
            'initialized': 'Initialized',
            'at breakpoint': 'At breakpoint',
            'zombie': 'Zombie',
            'unknown state': 'Unknown state',
        }

        if state_lower in state_display_map:
            return state_display_map[state_lower]

        # Fallback: capitalize first letter
        return raw_state[0].upper() + raw_state[1:] if raw_state else raw_state

    def _get_detailed_state(self, state: str, stack_trace: List[str], raw_state: Optional[str] = None) -> str:
        """Get detailed state information based on state and stack trace."""
        # For JVM internal threads with raw_state, use it directly
        if raw_state and not stack_trace:
            return self._format_raw_state(raw_state)

        if not stack_trace:
            return state

        stack_str = '\n'.join(stack_trace)

        if state == 'WAITING':
            if 'LockSupport.park(' in stack_str:
                return 'WAITING (Parking)'
            elif 'Object.wait(' in stack_str or 'Object.wait0(' in stack_str:
                return 'WAITING (Object.wait)'
            elif 'Condition.await(' in stack_str:
                return 'WAITING (Condition)'
            elif 'Thread.join(' in stack_str:
                return 'WAITING (Join)'
            else:
                return 'WAITING (Other)'

        elif state == 'TIMED_WAITING':
            if 'Thread.sleep(' in stack_str:
                return 'TIMED_WAITING (Sleep)'
            elif 'LockSupport.parkNanos(' in stack_str or 'LockSupport.parkUntil(' in stack_str:
                return 'TIMED_WAITING (Parking)'
            elif 'Object.wait(' in stack_str or 'Object.wait0(' in stack_str:
                return 'TIMED_WAITING (Object.wait)'
            else:
                return 'TIMED_WAITING (Other)'

        elif state == 'BLOCKED':
            return 'BLOCKED (Monitor)'

        elif state == 'RUNNABLE':
            if any(method in stack_str for method in ['java.net.SocketInputStream.socketRead0',
                                                      'java.net.SocketOutputStream.socketWrite0']):
                return 'RUNNABLE (Socket I/O)'
            elif any(method in stack_str for method in ['java.io.FileInputStream.read',
                                                        'java.io.FileOutputStream.write']):
                return 'RUNNABLE (File I/O)'
            else:
                return 'RUNNABLE (Active)'

        return state

    def _detect_pool_from_name(self, name: str) -> Optional[str]:
        """Detect thread pool name from thread name."""
        # GC threads from Java 8 style
        if '(ParallelGC)' in name or '(ConcurrentMarkSweepGC)' in name or '(G1 CollectedHeap)' in name or '(G1)' in name:
            gc_match = re.search(r'\((\w+GC|G1)\)', name)
            if gc_match:
                return gc_match.group(1)
        # G1 GC threads
        elif name.startswith('G1 Conc') or name.startswith('G1 Refine') or name == 'G1 Service' or name == 'G1 Main Marker':
            return 'G1GC'
        # GC threads from Java 11+
        elif name.startswith('GC Thread#') or name.startswith('GC task thread#'):
            return 'GCThreads'
        # Compiler threads
        elif re.match(r'C[12]\s+CompilerThread', name):
            return 'CompilerThreads'
        # Generic Java threads
        elif re.match(r'Thread-\d+$', name):
            return 'GenericThreads'
        # Special scheduler threads
        elif name in ['-job-', '-task-']:
            return 'SchedulerThreads'
        # Catalina utility threads
        elif name.startswith('Catalina-utility'):
            return 'CatalinaUtility'
        # Logback threads
        elif name.startswith('logback-'):
            return 'Logback'
        # JVM internal threads
        elif name in ['VM Thread', 'VM Periodic Task Thread', 'Reference Handler',
                      'Signal Dispatcher', 'Service Thread', 'Finalizer',
                      'InterruptTimer', 'GC Daemon', 'Sweeper thread',
                      'Monitor Deflation Thread', 'Notification Thread',
                      'Common-Cleaner']:
            return 'JVMInternalThreads'
        # Hikari threads
        elif 'Hikari' in name.lower():
            return 'HikariPool'
        # Threads with special suffixes
        elif name.endswith('-Acceptor') or name.endswith('-Poller'):
            return re.sub(r'-(Acceptor|Poller)$', '', name)
        # Pattern: extract everything before the last "-number"
        elif re.search(r'.*-\d+$', name):
            return re.sub(r'-\d+$', '', name)
        # Pattern with #: G1 Conc#0 -> G1 Conc
        elif re.search(r'.*#\d+$', name):
            return re.sub(r'#\d+$', '', name)
        # Other special threads - use full name as pool
        elif name in ['commons-pool-EvictionTimer', 'main',
                      'OracleTimeoutPollingThread',
                      'MultiThreadedHttpConnectionManager cleanup',
                      'Attach Listener', 'DestroyJavaVM',
                      'Monitor Ctrl-Break']:
            return name

        return None

    def _parse_deadlock(self, start_idx: int) -> int:
        """Parse deadlock information."""
        i = start_idx
        threads_involved = []
        description = []

        # Skip past header lines
        while i < len(self.raw_lines):
            line = self._strip_line_prefix(self.raw_lines[i]).strip()
            if not line:
                i += 1
                continue
            if "Found" in line and "deadlock" in line.lower():
                i += 1
                continue
            if line.startswith("="):
                i += 1
                continue
            break

        # Parse complete deadlock information
        while i < len(self.raw_lines):
            line = self._strip_line_prefix(self.raw_lines[i])
            line_stripped = line.strip()

            # Stop at the final summary line
            if "Found" in line_stripped and "deadlock" in line_stripped.lower() and "." in line_stripped:
                description.append(line_stripped)
                i += 1
                break

            # Stop if we hit a completely new section
            if not line_stripped and i + 1 < len(self.raw_lines):
                next_line = self._strip_line_prefix(self.raw_lines[i + 1]).strip()
                if next_line and (next_line.startswith('JNI global refs') or
                                 next_line.startswith('Heap')):
                    break

            # Extract thread names
            thread_match = re.search(r'^\s*"([^"]+)"\s*:', line)
            if thread_match:
                thread_name = thread_match.group(1)
                if thread_name not in threads_involved:
                    threads_involved.append(thread_name)

            description.append(line_stripped)
            i += 1

        if threads_involved:
            self.deadlocks.append(DeadlockInfo(
                threads=threads_involved,
                description="\n".join(description)
            ))

        return i


class Java8Parser(BaseThreadDumpParser):
    """Parser for Java 8 thread dumps."""

    def get_thread_header_pattern(self) -> re.Pattern:
        # Java 8: "name" #prio prio=X os_prio=X cpu=X elapsed=X tid=X nid=X state
        # Example: "Reference Handler" #2 daemon prio=10 os_prio=31 tid=0x... nid=0x... runnable
        # Example: "VM Thread" os_prio=31 tid=0x... nid=0x... runnable
        return re.compile(
            r'^"([^"]+)"'  # Thread name
            r'(?:\s+#(\d+))?'  # Optional #number
            r'(?:\s+daemon)?'  # Optional daemon
            r'(?:\s+prio=(\d+))?'  # Optional prio
            r'(?:\s+os_prio=(\d+))?'  # Optional os_prio
            r'(?:\s+cpu=([\d.]+\w+))?'  # Optional cpu
            r'(?:\s+elapsed=([\d.]+\w+))?'  # Optional elapsed
            r'(?:\s+tid=(0x[0-9a-f]+))?'  # Optional tid
            r'(?:\s+nid=(0x[0-9a-f]+))?'  # Optional nid
            r'(?:\s+(.+?))?$'  # Rest of line (state)
        )

    def parse_thread_header(self, line: str) -> Optional[dict]:
        match = self.get_thread_header_pattern().match(line)
        if not match:
            return None

        return {
            'name': match.group(1),
            'priority': int(match.group(3)) if match.group(3) else 0,
            'tid': match.group(7),
            'nid': match.group(8),
            'state_in_header': match.group(9) or '',
            'is_daemon': 'daemon' in line.lower()
        }

    def skip_smr_section(self, lines: List[str], start_idx: int) -> int:
        # Java 8 doesn't have SMR section
        return start_idx


class Java11Parser(BaseThreadDumpParser):
    """Parser for Java 11+ thread dumps (with SMR info)."""

    def get_thread_header_pattern(self) -> re.Pattern:
        # Java 11: "name" #daemon prio=X os_prio=X cpu=X elapsed=X tid=X nid=X state [address]
        # Also handles simplified format without cpu/elapsed or #number
        # Example: "Reference Handler" #2 daemon prio=10 os_prio=31 cpu=0.05ms elapsed=28.75s
        #          tid=0x... nid=0x... waiting on condition [0x...]
        # Example: "GC Thread#0" os_prio=0 cpu=3887.79ms elapsed=1442.30s tid=0x... nid=0x...
        return re.compile(
            r'^"([^"]+)"'  # Thread name
            r'(?:\s+#(\d+))?'  # Optional #number (some JVM threads like "GC Thread#0" don't have it outside quotes)
            r'(?:\s+daemon)?'  # Optional daemon
            r'(?:\s+prio=(\d+))?'  # Optional prio
            r'(?:\s+os_prio=(\d+))?'  # Optional os_prio
            r'(?:\s+cpu=([\d.]+\w+))?'  # Optional cpu
            r'(?:\s+elapsed=([\d.]+\w+))?'  # Optional elapsed
            r'(?:\s+tid=(0x[0-9a-f]+))?'  # Optional tid
            r'(?:\s+nid=(0x[0-9a-f]+))?'  # Optional nid (some JVM internal threads might not have it)
            r'(?:\s+(.+?))?$'  # Rest of line (state + address)
        )

    def parse_thread_header(self, line: str) -> Optional[dict]:
        match = self.get_thread_header_pattern().match(line)
        if not match:
            return None

        # Extract optional fields
        prio = match.group(3)
        os_prio = match.group(4)

        return {
            'name': match.group(1),
            'priority': int(prio) if prio else 0,
            'tid': match.group(7),
            'nid': match.group(8),
            'cpu_time': match.group(5),
            'elapsed_time': match.group(6),
            'state_in_header': match.group(9) or '',
            'is_daemon': 'daemon' in line.lower()
        }

    def skip_smr_section(self, lines: List[str], start_idx: int) -> int:
        # Skip SMR section: "Threads class SMR info:" followed by thread list
        i = start_idx
        while i < len(lines):
            stripped_line = self._strip_line_prefix(lines[i])
            if "Threads class SMR info" in stripped_line:
                # Skip until we find an empty line or a thread header
                i += 1
                while i < len(lines) and not self._strip_line_prefix(lines[i]).strip().startswith('"'):
                    i += 1
                return i
            if stripped_line.strip().startswith('"'):
                return i
            i += 1
        return start_idx


class Java21Parser(BaseThreadDumpParser):
    """Parser for Java 21+ thread dumps (with decimal nid in header)."""

    def get_thread_header_pattern(self) -> re.Pattern:
        # Java 21: "name" #[decimal_nid] daemon prio=X os_prio=X cpu=X elapsed=X tid=X nid=decimal state [address]
        # Also handles simplified format without [decimal_nid] and with hex nid, or without #number
        # Standard: "Reference Handler" #9 [24323] daemon prio=10 os_prio=31 cpu=0.07ms elapsed=39.31s tid=0x... nid=24323 waiting on condition [0x...]
        # Simplified: "Attach Listener" #14 daemon prio=9 os_prio=31 tid=0x... nid=0x... waiting on condition [0x...]
        # GC threads: "GC Thread#0" os_prio=31 cpu=0.02ms elapsed=39.32s tid=0x... nid=0x... runnable
        return re.compile(
            r'^"([^"]+)"'  # Thread name
            r'(?:\s+#(\d+))?'  # Optional #number (some JVM threads like "GC Thread#0" don't have it outside quotes)
            r'(?:\s+\[(\d+)\])?'  # Optional [decimal_nid]
            r'(?:\s+daemon)?'  # Optional daemon
            r'(?:\s+prio=(\d+))?'  # Optional prio (some JVM threads might not have it)
            r'(?:\s+os_prio=(\d+))?'  # Optional os_prio
            r'(?:\s+cpu=([\d.]+\w+))?'  # Optional cpu
            r'(?:\s+elapsed=([\d.]+\w+))?'  # Optional elapsed
            r'(?:\s+tid=(0x[0-9a-f]+))?'  # Optional tid (JVM internal threads might not have it)
            r'(?:\s+nid=(0x[0-9a-f]+|\d+))?'  # Optional nid (hex or decimal!)
            r'(?:\s+(.+?))?$'  # Rest of line (state + address)
        )

    def parse_thread_header(self, line: str) -> Optional[dict]:
        match = self.get_thread_header_pattern().match(line)
        if not match:
            return None

        # Extract nid and convert to hex if needed
        nid = match.group(9)
        if nid and nid.isdigit():  # Decimal nid
            nid = f"0x{int(nid):x}"

        # Extract other fields - they are optional now
        prio = match.group(4)
        os_prio = match.group(5)

        return {
            'name': match.group(1),
            'priority': int(prio) if prio else 0,
            'tid': match.group(8),
            'nid': nid,
            'cpu_time': match.group(6),
            'elapsed_time': match.group(7),
            'state_in_header': match.group(10) or '',
            'is_daemon': 'daemon' in line.lower()
        }

    def skip_smr_section(self, lines: List[str], start_idx: int) -> int:
        # Same as Java 11
        i = start_idx
        while i < len(lines):
            stripped_line = self._strip_line_prefix(lines[i])
            if "Threads class SMR info" in stripped_line:
                i += 1
                while i < len(lines) and not self._strip_line_prefix(lines[i]).strip().startswith('"'):
                    i += 1
                return i
            if stripped_line.strip().startswith('"'):
                return i
            i += 1
        return start_idx


class Java25Parser(Java21Parser):
    """Parser for Java 25 thread dumps (same format as Java 21)."""

    pass


def detect_java_version(content: str) -> int:
    """Detect Java version from thread dump content.

    Detection logic:
    1. Check for SMR section - Java 8 does NOT have "Threads class SMR info"
    2. For Java 11+, use version number from "Full thread dump" line
    """
    # Primary check: Java 8 does NOT have SMR info
    if "Threads class SMR info" not in content:
        return 8

    # Has SMR info, so it's Java 11 or later - use version number
    version_match = re.search(r'Full thread dump.*?\((\d+)\.', content)
    if version_match:
        major_version = int(version_match.group(1))
        # Map version: 11, 17, 21, 25
        if major_version in [8, 11, 17, 21, 25]:
            return major_version
        # For other future versions, return as-is
        return major_version

    # Fallback if version number not found
    return 11


def extract_java_version_string(content: str) -> Optional[str]:
    """Extract full Java version string from thread dump.

    Returns the version string like "11.0.27+6-LTS mixed mode" or "25.452-b09 mixed mode".
    Returns None if not found.

    Handles different formats:
    - Java 11+: "Full thread dump OpenJDK 64-Bit Server VM (17.0.7+7 mixed mode, sharing):"
    - Java 8:   "Full thread dump Java HotSpot(TM) 64-Bit Server VM (25.201-b09 mixed mode):"
    """
    # Try to match the version in parentheses at the end of the line
    # Look for patterns like: (XX.XXX+XX mixed mode) or (XX.XXX-bXX mixed mode)
    version_match = re.search(r'Full thread dump.*\((\d+\.[\d.+]+-b\d+|\d+\.[\d.+]+\+[\d]+-?LTS?[\w\s]*mixed mode[^)]*)\)', content)
    if version_match:
        return version_match.group(1).strip()

    # Fallback: match last parentheses on the "Full thread dump" line
    for line in content.split('\n'):
        if 'Full thread dump' in line:
            # Find all parentheses pairs on this line
            parens = re.findall(r'\(([^)]+)\)', line)
            if parens:
                # Return the last one (which should be the version for Java 8 format)
                # For Java 11+, there's usually only one, so this works too
                return parens[-1].strip()

    return None


def extract_timestamp(content: str) -> Optional[str]:
    """Extract timestamp from the "Full thread dump" line or the line before it.

    Returns the timestamp string like "2025-11-25T14:27:11.443-0800" or "2026-01-01 19:58:06" or None if not found.

    Handles formats:
    - "2025-11-25T14:27:11.443-0800 [190088] Full thread dump ..." (timestamp on same line)
    - "2024-07-29T23:49:19.102-0700 [8526] Full thread dump ..." (timestamp on same line)
    - "2026-01-01 19:58:06" followed by "Full thread dump ..." (timestamp on previous line)
    """
    lines = content.split('\n')
    for i, line in enumerate(lines):
        if 'Full thread dump' in line:
            # First, check if timestamp is at the beginning of the same line
            # ISO 8601 format: YYYY-MM-DDTHH:MM:SS.mmm+ZZZZ
            timestamp_match = re.match(r'^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+[+-]\d{4})', line)
            if timestamp_match:
                return timestamp_match.group(1)

            # Second, check if the previous line contains a timestamp
            # Format: YYYY-MM-DD HH:MM:SS
            if i > 0:
                prev_line = lines[i - 1].strip()
                # Match simple date-time format: YYYY-MM-DD HH:MM:SS
                simple_timestamp_match = re.match(r'^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})$', prev_line)
                if simple_timestamp_match:
                    return simple_timestamp_match.group(1)

            break
    return None


def create_parser(content: str) -> BaseThreadDumpParser:
    """Factory function to create appropriate parser based on Java version."""
    version = detect_java_version(content)

    if version >= 25:
        return Java25Parser()
    elif version >= 21:
        return Java21Parser()
    elif version >= 11:
        return Java11Parser()
    else:
        return Java8Parser()


# Backward compatibility: create a wrapper class
class ThreadDumpParser:
    """Wrapper class for backward compatibility."""

    def __init__(self, content: str = None):
        # If content provided, create parser immediately
        # Otherwise, parse() will handle it
        self._content = content
        self._parser = None

    def parse(self, content: str = None) -> Tuple[List[ThreadInfo], List[DeadlockInfo]]:
        """Parse thread dump content."""
        # Use content from parse() if provided, otherwise use constructor content
        parse_content = content or self._content
        if not parse_content:
            raise ValueError("No content provided to parse")

        # Create parser based on content
        parser = create_parser(parse_content)
        return parser.parse(parse_content)
