"""Tests for thread state mapping and thread pool detection."""

import pytest
from app.core.parser import Java21Parser


class TestStateMapping:
    """Test thread state mapping."""

    def test_map_runnable_states(self):
        parser = Java21Parser()

        assert parser._map_raw_state_to_standard('runnable') == 'RUNNABLE'
        assert parser._map_raw_state_to_standard('allocated') == 'RUNNABLE'
        assert parser._map_raw_state_to_standard('initialized') == 'RUNNABLE'
        assert parser._map_raw_state_to_standard('at breakpoint') == 'RUNNABLE'

    def test_map_blocked_states(self):
        parser = Java21Parser()

        assert parser._map_raw_state_to_standard('waiting for monitor entry') == 'BLOCKED'
        assert parser._map_raw_state_to_standard('waiting to lock') == 'BLOCKED'

    def test_map_waiting_states(self):
        parser = Java21Parser()

        assert parser._map_raw_state_to_standard('waiting on condition') == 'WAITING'
        assert parser._map_raw_state_to_standard('in object.wait()') == 'WAITING'

    def test_map_timed_waiting_states(self):
        parser = Java21Parser()

        assert parser._map_raw_state_to_standard('sleeping') == 'TIMED_WAITING'

    def test_map_unknown_states(self):
        parser = Java21Parser()

        assert parser._map_raw_state_to_standard('zombie') == 'UNKNOWN'
        assert parser._map_raw_state_to_standard('unknown state') == 'UNKNOWN'
        assert parser._map_raw_state_to_standard('random gibberish') == 'UNKNOWN'

    def test_format_raw_state(self):
        parser = Java21Parser()

        assert parser._format_raw_state('runnable') == 'Runnable'
        assert parser._format_raw_state('waiting on condition') == 'Waiting on condition'
        assert parser._format_raw_state('waiting for monitor entry') == 'Waiting for monitor entry'
        assert parser._format_raw_state('sleeping') == 'Sleeping'

    def test_get_detailed_state_for_waiting(self):
        parser = Java21Parser()

        # Waiting with park - use actual LockSupport method
        stack = ['java.util.concurrent.locks.LockSupport.park(LockSupport.java:123)']
        assert parser._get_detailed_state('WAITING', stack) == 'WAITING (Parking)'

        # Waiting with Object.wait
        stack = ['java.lang.Object.wait0(Native Method)']
        assert parser._get_detailed_state('WAITING', stack) == 'WAITING (Object.wait)'

        # Waiting with Condition - must match 'Condition.await(' pattern
        stack = ['java.util.concurrent.locks.Condition.await()']
        assert parser._get_detailed_state('WAITING', stack) == 'WAITING (Condition)'

        # Waiting with Join
        stack = ['java.lang.Thread.join(Thread.java:1234)']
        assert parser._get_detailed_state('WAITING', stack) == 'WAITING (Join)'

    def test_get_detailed_state_for_timed_waiting(self):
        parser = Java21Parser()

        # Timed waiting with sleep
        stack = ['java.lang.Thread.sleep(Native Method)']
        assert parser._get_detailed_state('TIMED_WAITING', stack) == 'TIMED_WAITING (Sleep)'

        # Timed waiting with parkNanos
        stack = ['java.util.concurrent.locks.LockSupport.parkNanos(Native Method)']
        assert parser._get_detailed_state('TIMED_WAITING', stack) == 'TIMED_WAITING (Parking)'

    def test_get_detailed_state_for_runnable(self):
        parser = Java21Parser()

        # Runnable with Socket I/O
        stack = ['java.net.SocketInputStream.socketRead0']
        assert parser._get_detailed_state('RUNNABLE', stack) == 'RUNNABLE (Socket I/O)'

        # Runnable with File I/O
        stack = ['java.io.FileInputStream.read']
        assert parser._get_detailed_state('RUNNABLE', stack) == 'RUNNABLE (File I/O)'

        # Runnable active
        stack = ['com.example.MyClass.myMethod']
        assert parser._get_detailed_state('RUNNABLE', stack) == 'RUNNABLE (Active)'


class TestThreadPoolDetection:
    """Test thread pool name detection."""

    def test_detect_compiler_threads(self):
        parser = Java21Parser()

        assert parser._detect_pool_from_name('C1 CompilerThread0') == 'CompilerThreads'
        assert parser._detect_pool_from_name('C2 CompilerThread1') == 'CompilerThreads'

    def test_detect_generic_threads(self):
        parser = Java21Parser()

        assert parser._detect_pool_from_name('Thread-1') == 'GenericThreads'
        assert parser._detect_pool_from_name('Thread-100') == 'GenericThreads'

    def test_detect_jvm_internal_threads(self):
        parser = Java21Parser()

        assert parser._detect_pool_from_name('VM Thread') == 'JVMInternalThreads'
        assert parser._detect_pool_from_name('Reference Handler') == 'JVMInternalThreads'
        assert parser._detect_pool_from_name('Signal Dispatcher') == 'JVMInternalThreads'
        assert parser._detect_pool_from_name('Finalizer') == 'JVMInternalThreads'

    def test_detect_catalina_utility(self):
        parser = Java21Parser()

        assert parser._detect_pool_from_name('Catalina-utility-1') == 'CatalinaUtility'

    def test_detect_logback_threads(self):
        parser = Java21Parser()

        assert parser._detect_pool_from_name('logback-1') == 'Logback'

    def test_detect_hikari_pool(self):
        parser = Java21Parser()

        # Hikari detection checks for 'hikari' (lowercase) in the name
        assert parser._detect_pool_from_name('HikariPool-1') == 'HikariPool'
        # Test with actual Hikari thread names (without numbers that get stripped)
        assert parser._detect_pool_from_name('HikariPool-housekeeper') == 'HikariPool'

    def test_detect_special_threads(self):
        parser = Java21Parser()

        assert parser._detect_pool_from_name('main') == 'main'
        assert parser._detect_pool_from_name('Attach Listener') == 'Attach Listener'

    def test_detect_pool_suffix_patterns(self):
        parser = Java21Parser()

        # Remove -Acceptor or -Poller suffix
        assert parser._detect_pool_from_name('http-nio-8080-Acceptor') == 'http-nio-8080'
        assert parser._detect_pool_from_name('http-nio-8080-Poller') == 'http-nio-8080'

        # Remove trailing -number
        assert parser._detect_pool_from_name('pool-1-thread-1') == 'pool-1-thread'
        assert parser._detect_pool_from_name('pool-2-worker-100') == 'pool-2-worker'

    def test_detect_no_pool(self):
        parser = Java21Parser()

        assert parser._detect_pool_from_name('RandomThreadName') is None


class TestPrefixDetection:
    """Test timestamp/prefix detection and stripping."""

    def test_detect_timestamp_prefix(self):
        parser = Java21Parser()
        content = '2025-11-25T14:27:11.443-0800 [190088] Full thread dump OpenJDK 64-Bit Server VM'

        skip = parser._detect_prefix_skip(content)
        assert skip == len('2025-11-25T14:27:11.443-0800 [190088] ')

    def test_detect_no_prefix(self):
        parser = Java21Parser()
        content = 'Full thread dump OpenJDK 64-Bit Server VM'

        skip = parser._detect_prefix_skip(content)
        assert skip == 0

    def test_strip_line_with_prefix(self):
        parser = Java21Parser()
        parser.prefix_skip = 30

        line = '012345678901234567890123456789"Thread" prio=5'
        stripped = parser._strip_line_prefix(line)
        assert stripped == '"Thread" prio=5'

    def test_strip_line_without_prefix(self):
        parser = Java21Parser()
        parser.prefix_skip = 0

        line = '"Thread" prio=5'
        stripped = parser._strip_line_prefix(line)
        assert stripped == '"Thread" prio=5'
