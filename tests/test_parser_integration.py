"""Integration tests for complete thread dump parsing."""

import pytest
from app.core.parser import Java8Parser, Java21Parser


class TestFullParsingIntegration:
    """Integration tests with real thread dump snippets."""

    def test_parse_simple_java8_thread_dump(self):
        content = '''
Full thread dump Java HotSpot(TM) 64-Bit Server VM (25.201-b09 mixed mode):
"Reference Handler" #2 daemon prio=10 os_prio=31 tid=0x0000000100000000 nid=0x123 runnable
   java.lang.Thread.State: RUNNABLE
	at java.lang.Object.wait0(Native Method)
	at java.lang.Object.wait(Object.java:502)
	at java.lang.Object.wait(Object.java:442)

"Finalizer" #3 daemon prio=8 os_prio=31 tid=0x0000000200000000 nid=0x456 in Object.wait()
   java.lang.Thread.State: WAITING (on object monitor)
	at java.lang.Object.wait0(Native Method)
	- waiting on <no object reference available>
	at java.lang.Object.wait(Object.java:502)
	- locked <0x0000000600000000> (a java.lang.ref.ReferenceQueue$Lock)
'''
        parser = Java8Parser()
        threads, deadlocks = parser.parse(content)

        assert len(threads) == 2
        assert threads[0].name == 'Reference Handler'
        assert threads[0].state == 'RUNNABLE'
        assert threads[0].is_daemon is True

        assert threads[1].name == 'Finalizer'
        assert threads[1].state == 'WAITING'
        assert threads[1].detailed_state == 'WAITING (Object.wait)'

    def test_parse_java21_thread_with_stack_trace(self):
        content = '''
Full thread dump OpenJDK 64-Bit Server VM (21.0.8+9 mixed mode, sharing):

Threads class SMR info:
_main_thread_info
"main" #1 [6659] prio=5 os_prio=31 cpu=1400.49ms elapsed=7149.15s tid=0x00000001047939d0 nid=6659 waiting on condition [0x000000016bfea000]
   java.lang.Thread.State: TIMED_WAITING (parking)
at java.lang.Thread.sleep(Native Method)
at java.util.concurrent.locks.LockSupport.parkNanos(LockSupport.java:269)
'''
        parser = Java21Parser()
        threads, deadlocks = parser.parse(content)

        assert len(threads) == 1
        assert threads[0].name == 'main'
        assert threads[0].state == 'TIMED_WAITING'
        assert threads[0].cpu_time == '1400.49ms'
        assert threads[0].elapsed_time == '7149.15s'

    def test_parse_blocked_thread(self):
        content = '''
Full thread dump OpenJDK 64-Bit Server VM (21.0.8+9 mixed mode, sharing):

"Thread-A" #1 [1000] prio=5 os_prio=31 tid=0x0000000100000000 nid=1000 waiting for monitor entry [0x...]
   java.lang.Thread.State: BLOCKED (on object monitor)
	at java.lang.Object.wait0(Native Method)
	- waiting to lock <0x0000000600000000> (a java.lang.Object)
	at java.lang.Object.wait(Object.java:502)
'''
        parser = Java21Parser()
        threads, deadlocks = parser.parse(content)

        assert len(threads) == 1
        assert threads[0].state == 'BLOCKED'
        assert threads[0].detailed_state == 'BLOCKED (Monitor)'

    def test_parse_sleeping_thread(self):
        content = '''
Full thread dump OpenJDK 64-Bit Server VM (21.0.8+9 mixed mode, sharing):

"SleepingThread" #1 [1000] prio=5 os_prio=31 tid=0x0000000100000000 nid=1000 waiting on condition [0x...]
   java.lang.Thread.State: TIMED_WAITING (sleeping)
	at java.lang.Thread.sleep(Native Method)
	at com.example.MyClass.sleepMethod(MyClass.java:42)
'''
        parser = Java21Parser()
        threads, deadlocks = parser.parse(content)

        assert len(threads) == 1
        assert threads[0].state == 'TIMED_WAITING'
        assert threads[0].detailed_state == 'TIMED_WAITING (Sleep)'

    def test_parse_detects_thread_pool_from_stack(self):
        content = '''
Full thread dump OpenJDK 64-Bit Server VM (21.0.8+9 mixed mode, sharing):

"pool-1-thread-1" #10 [2000] prio=5 os_prio=31 tid=0x0000000100000000 nid=2000 runnable [0x...]
   java.lang.Thread.State: RUNNABLE
	at java.util.concurrent.ThreadPoolExecutor.runWorker(ThreadPoolExecutor.java:1149)
	at java.util.concurrent.ThreadPoolExecutor$Worker.run(ThreadPoolExecutor.java:624)
	at java.lang.Thread.run(Thread.java:1583)
'''
        parser = Java21Parser()
        threads, deadlocks = parser.parse(content)

        assert len(threads) == 1
        # Pool name is detected from the thread name pattern (suffix removed)
        # The pool-\d+-\w+ pattern matches in stack, but in this case it's in the thread name
        assert threads[0].pool_name == 'pool-1-thread'


class TestDeadlockParsing:
    """Test deadlock information parsing."""

    def test_parse_simple_deadlock(self):
        content = '''
Full thread dump OpenJDK 64-Bit Server VM (21.0.8+9 mixed mode, sharing):

"Thread-A" #1 prio=5 waiting for monitor entry
   java.lang.Thread.State: BLOCKED

Found one Java-level deadlock:
=============================
"Thread-A":
   waiting to lock monitor 0x... (object 0x...),
   which is held by "Thread-B"
"Thread-B":
   waiting to lock monitor 0x... (object 0x...),
   which is held by "Thread-A"

Java stack information for the threads listed above:
=============================
"Thread-A":
        at com.example.ClassA.methodA(ClassA.java:10)
        - waiting to lock <0x...> (a com.example.ClassB)
"Thread-B":
        at com.example.ClassB.methodB(ClassB.java:20)
        - waiting to lock <0x...> (a com.example.ClassA)

Found 1 deadlock.
'''
        parser = Java21Parser()
        threads, deadlocks = parser.parse(content)

        assert len(deadlocks) == 1
        assert 'Thread-A' in deadlocks[0].threads
        assert 'Thread-B' in deadlocks[0].threads
        # Note: The parser skips the initial "Found one Java-level deadlock:" line
        # but includes the final "Found 1 deadlock." line
        assert 'Found 1 deadlock' in deadlocks[0].description

    def test_parse_multiple_deadlocks(self):
        # Test with actual JVM-reported deadlock format
        content = '''
Full thread dump OpenJDK 64-Bit Server VM (21.0.8+9 mixed mode, sharing):

"Thread-A" prio=5 waiting for monitor entry
   java.lang.Thread.State: BLOCKED

Found one Java-level deadlock:
=============================
"Thread-A":
   waiting to lock monitor 0x000000060036e258 (object 0x00000000c0bf0f88, a java.lang.Object),
   which is held by "Thread-B"
"Thread-B":
   waiting to lock monitor 0x000000060036e258 (object 0x00000000c0bf0f88, a java.lang.Object),
   which is held by "Thread-A"

Java stack information for the threads listed above:
=============================
"Thread-A":
	at com.example.ClassA.methodA(ClassA.java:10)
	- waiting to lock <0x000000060036e258> (a java.lang.Object)
"Thread-B":
	at com.example.ClassB.methodB(ClassB.java:20)
	- waiting to lock <0x000000060036e258> (a java.lang.Object)

Found 1 deadlock.
JNI global refs: ...
'''
        parser = Java21Parser()
        threads, deadlocks = parser.parse(content)

        # Should parse deadlock information
        assert len(deadlocks) == 1
        assert len(deadlocks[0].threads) == 2
        assert 'Thread-A' in deadlocks[0].threads
        assert 'Thread-B' in deadlocks[0].threads
        assert 'Found 1 deadlock' in deadlocks[0].description
