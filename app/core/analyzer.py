"""Thread dump analyzer."""

from typing import Dict, List
from collections import Counter
from app.models.thread_data import ThreadInfo, ThreadStatistics


class ThreadAnalyzer:
    """Analyze parsed thread data."""

    def __init__(self, threads: List[ThreadInfo], java_version: str = None, timestamp: str = None):
        self.threads = threads
        self.java_version = java_version
        self.timestamp = timestamp

    def analyze(self) -> ThreadStatistics:
        """
        Perform comprehensive analysis on thread data.

        Returns:
            ThreadStatistics object with all analysis results
        """
        total_threads = len(self.threads)

        # Count thread states
        state_distribution = self._analyze_states()
        detailed_state_distribution = self._analyze_detailed_states()

        # Identify thread pools
        thread_pools = self._analyze_pools()
        thread_pools_detailed = self._analyze_pools_detailed()

        # Identify thread groups
        thread_groups = self._analyze_groups()

        # Count daemon vs non-daemon
        daemon_count = sum(1 for t in self.threads if t.is_daemon)
        non_daemon_count = total_threads - daemon_count

        # Count GC threads
        gc_count = self._count_gc_threads()

        return ThreadStatistics(
            total_threads=total_threads,
            java_version=self.java_version,
            timestamp=self.timestamp,
            state_distribution=state_distribution,
            detailed_state_distribution=detailed_state_distribution,
            thread_pools=thread_pools,
            thread_pools_detailed=thread_pools_detailed,
            thread_groups=thread_groups,
            daemon_threads=daemon_count,
            non_daemon_threads=non_daemon_count,
            gc_threads=gc_count
        )

    def _analyze_states(self) -> Dict[str, int]:
        """Analyze thread state distribution."""
        states = [thread.state for thread in self.threads]
        return dict(Counter(states))

    def _analyze_detailed_states(self) -> Dict[str, int]:
        """Analyze detailed thread state distribution."""
        states = [thread.detailed_state or thread.state for thread in self.threads]
        return dict(Counter(states))

    def _analyze_pools(self) -> Dict[str, int]:
        """Analyze thread pool distribution."""
        pools = {}
        for thread in self.threads:
            pool_name = thread.pool_name or "No Pool"
            pools[pool_name] = pools.get(pool_name, 0) + 1
        return dict(sorted(pools.items(), key=lambda x: x[1], reverse=True))

    def _analyze_pools_detailed(self) -> Dict[str, Dict[str, int]]:
        """Analyze thread pool distribution with state breakdown."""
        pools_detailed = {}
        for thread in self.threads:
            pool_name = thread.pool_name or "No Pool"
            if pool_name not in pools_detailed:
                pools_detailed[pool_name] = {}

            # Use detailed state if available, otherwise use basic state
            state = thread.detailed_state or thread.state
            pools_detailed[pool_name][state] = pools_detailed[pool_name].get(state, 0) + 1

        # Sort pools by total count
        sorted_pools = dict(sorted(
            pools_detailed.items(),
            key=lambda x: sum(x[1].values()),
            reverse=True
        ))
        return sorted_pools

    def _analyze_groups(self) -> Dict[str, int]:
        """Analyze thread group distribution."""
        groups = {}
        for thread in self.threads:
            group_name = thread.thread_group or "No Group"
            groups[group_name] = groups.get(group_name, 0) + 1
        return dict(sorted(groups.items(), key=lambda x: x[1], reverse=True))

    def get_top_cpu_threads(self, n: int = 10) -> List[ThreadInfo]:
        """
        Get threads with highest CPU time.

        Args:
            n: Number of threads to return

        Returns:
            List of ThreadInfo sorted by CPU time
        """
        # Filter threads with CPU time and sort
        threads_with_cpu = [t for t in self.threads if t.cpu_time]

        # Sort by CPU time (parse the value like "14929.56ms")
        def get_cpu_ms(thread: ThreadInfo) -> float:
            if not thread.cpu_time:
                return 0.0
            value_str = thread.cpu_time.lower()
            try:
                if "ms" in value_str:
                    return float(value_str.replace("ms", ""))
                elif "s" in value_str:
                    return float(value_str.replace("s", "")) * 1000
                elif "us" in value_str:
                    return float(value_str.replace("us", "")) / 1000
            except (ValueError, AttributeError):
                return 0.0
            return 0.0

        return sorted(threads_with_cpu, key=get_cpu_ms, reverse=True)[:n]

    def get_blocked_threads(self) -> List[ThreadInfo]:
        """Get all blocked threads."""
        return [t for t in self.threads if "BLOCKED" in t.state.upper()]

    def get_waiting_threads(self) -> List[ThreadInfo]:
        """Get all waiting threads (including TIMED_WAITING)."""
        return [t for t in self.threads if "WAITING" in t.state.upper()]

    def detect_potential_deadlocks(self, jvm_deadlock_threads: set = None) -> List[Dict]:
        """
        Detect potential deadlocks by analyzing lock dependencies.

        Args:
            jvm_deadlock_threads: Set of thread pairs already reported by JVM (to avoid duplicates)

        Returns:
            List of potential deadlock descriptions
        """
        import re
        from collections import defaultdict

        if jvm_deadlock_threads is None:
            jvm_deadlock_threads = set()

        # Build lock dependency graph
        # locks_held[thread_name] = set of lock addresses held by thread
        # waiting_for[thread_name] = lock address the thread is waiting for
        locks_held = defaultdict(set)
        waiting_for = {}

        # Pattern to extract lock addresses from stack traces
        locked_pattern = re.compile(r'- locked <(0x[0-9a-f]+)>')
        waiting_on_pattern = re.compile(r'- waiting on <(0x[0-9a-f]+)>')
        waiting_to_lock_pattern = re.compile(r'- waiting to lock <(0x[0-9a-f]+)>')
        parking_to_wait_pattern = re.compile(r'- parking to wait for\s+<(0x[0-9a-f]+)>')

        for thread in self.threads:
            thread_name = thread.name
            held_locks = set()
            waiting_lock = None

            # Analyze stack trace
            for line in thread.stack_trace:
                # Find locks held by this thread
                for match in locked_pattern.finditer(line):
                    held_locks.add(match.group(1))

                # Find lock the thread is waiting for
                if not waiting_lock:
                    match = waiting_on_pattern.search(line)
                    if match:
                        waiting_lock = match.group(1)
                        continue

                    match = waiting_to_lock_pattern.search(line)
                    if match:
                        waiting_lock = match.group(1)
                        continue

                    match = parking_to_wait_pattern.search(line)
                    if match:
                        waiting_lock = match.group(1)
                        continue

            if held_locks:
                locks_held[thread_name].update(held_locks)

            if waiting_lock:
                waiting_for[thread_name] = waiting_lock

        # Detect cycles in the lock dependency graph
        potential_deadlocks = []

        # For each waiting thread, check if the lock it's waiting for is held by another thread
        for waiting_thread, waiting_lock in waiting_for.items():
            # Find which thread holds the lock we're waiting for (excluding self-wait)
            holding_threads = []
            for thread_name, held_locks_set in locks_held.items():
                if waiting_lock in held_locks_set and thread_name != waiting_thread:
                    holding_threads.append(thread_name)

            for holding_thread in holding_threads:
                # Create thread pair tuple for comparison
                thread_pair = tuple(sorted([waiting_thread, holding_thread]))

                # Skip if JVM already reported this deadlock
                if thread_pair in jvm_deadlock_threads:
                    continue

                # Check if this is a nested monitor deadlock pattern:
                # - holding_thread holds locks and is in wait state
                # - waiting_thread is blocked/waiting trying to acquire one of those locks
                potential_deadlocks.append({
                    'type': 'Potential Deadlock (Nested Monitor)',
                    'cycle': f"{waiting_thread} (blocked) -> {holding_thread} (waiting)",
                    'description': (
                        f"{holding_thread} holds {len(locks_held[holding_thread])} lock(s) including {waiting_lock}, "
                        f"and is in a wait state\n"
                        f"{waiting_thread} is blocked trying to acquire lock {waiting_lock}"
                    ),
                    'threads': sorted([waiting_thread, holding_thread])
                })

        # Remove duplicates (same thread pair)
        seen = set()
        unique_deadlocks = []
        for dl in potential_deadlocks:
            thread_pair = tuple(dl['threads'])
            if thread_pair not in seen:
                seen.add(thread_pair)
                unique_deadlocks.append(dl)

        return unique_deadlocks

    def _count_gc_threads(self) -> int:
        """
        Count GC (Garbage Collection) threads.

        GC threads are identified by common naming patterns:
        - "GC" in the thread name (e.g., "G1 Young Generation", "G1 Old Generation")
        - Common GC worker patterns (e.g., "G1 Par", "Parallel GC", "CMS", "ZGC", "Shenandoah")

        Note: CompilerThread is NOT counted as GC thread (it's JIT compilation, separate from GC)

        Returns:
            Count of GC threads
        """
        gc_count = 0
        gc_patterns = [
            'G1 Young',
            'G1 Old',
            'G1 Conc',  # G1 Concurrent threads (e.g., "G1 Conc#0")
            'G1 Concurrent',
            'G1 Par',
            'G1 Refine',
            'G1 Service',
            'G1 Main',  # G1 Main Marker thread
            'ParallelGC',
            'Parallel GC',
            'CMS',
            'ZGC',
            'Shenandoah',
            'GC Thread',
            'GC task thread',  # Java 8 ParallelGC worker threads
            'GC Daemon',  # Java 8 GC daemon thread
            'GCTask',
        ]

        for thread in self.threads:
            thread_name_upper = thread.name.upper()
            # Check if any GC pattern is in the thread name
            for pattern in gc_patterns:
                if pattern.upper() in thread_name_upper:
                    gc_count += 1
                    break

        return gc_count
