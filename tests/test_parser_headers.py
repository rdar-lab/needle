"""Tests for parser-specific header parsing logic."""

import pytest
from app.core.parser import (
    Java8Parser,
    Java11Parser,
    Java21Parser,
    Java25Parser,
)


class TestJava8Parser:
    """Test Java 8 specific parser."""

    def test_parse_simple_thread_header(self):
        parser = Java8Parser()
        line = '"Reference Handler" #2 daemon prio=10 os_prio=31 tid=0x0000000100000000 nid=0x123 runnable'
        result = parser.parse_thread_header(line)

        assert result is not None
        assert result['name'] == 'Reference Handler'
        assert result['priority'] == 10
        assert result['tid'] == '0x0000000100000000'
        assert result['nid'] == '0x123'
        assert result['state_in_header'] == 'runnable'
        assert result['is_daemon'] is True

    def test_parse_vm_thread_header(self):
        parser = Java8Parser()
        line = '"VM Thread" os_prio=31 tid=0x0000000100000000 nid=0x123 runnable'
        result = parser.parse_thread_header(line)

        assert result is not None
        assert result['name'] == 'VM Thread'
        assert result['priority'] == 0  # No prio field
        assert result['is_daemon'] is False

    def test_parse_non_daemon_thread(self):
        parser = Java8Parser()
        line = '"main" #1 prio=5 os_prio=31 tid=0x0000000100000000 nid=0x123 runnable'
        result = parser.parse_thread_header(line)

        assert result is not None
        assert result['name'] == 'main'
        assert result['is_daemon'] is False

    def test_skip_smr_section_java8(self):
        parser = Java8Parser()
        lines = ['Full thread dump', '"Thread" prio=5']
        assert parser.skip_smr_section(lines, 0) == 0


class TestJava11Parser:
    """Test Java 11 specific parser."""

    def test_parse_standard_thread_header(self):
        parser = Java11Parser()
        line = '"Reference Handler" #2 daemon prio=10 os_prio=31 cpu=0.05ms elapsed=28.75s tid=0x0000000100000000 nid=0x123 waiting on condition [0x...]'
        result = parser.parse_thread_header(line)

        assert result is not None
        assert result['name'] == 'Reference Handler'
        assert result['priority'] == 10
        assert result['cpu_time'] == '0.05ms'
        assert result['elapsed_time'] == '28.75s'
        assert result['tid'] == '0x0000000100000000'
        assert result['nid'] == '0x123'

    def test_parse_gc_thread_header(self):
        parser = Java11Parser()
        line = '"GC Thread#0" os_prio=0 cpu=3887.79ms elapsed=1442.30s tid=0x0000000100000000 nid=0x123 runnable'
        result = parser.parse_thread_header(line)

        assert result is not None
        assert result['name'] == 'GC Thread#0'
        assert result['priority'] == 0
        assert result['is_daemon'] is False

    def test_skip_smr_section_java11(self):
        parser = Java11Parser()
        lines = [
            'Full thread dump',
            'Threads class SMR info:',
            '_java_thread_list=0x0000000100000000, length=1',
            '"Thread" prio=5'
        ]
        result = parser.skip_smr_section(lines, 0)
        assert result == 3  # Should skip to the thread header


class TestJava21Parser:
    """Test Java 21 specific parser."""

    def test_parse_standard_thread_with_decimal_nid(self):
        parser = Java21Parser()
        line = '"Reference Handler" #9 [24323] daemon prio=10 os_prio=31 cpu=0.07ms elapsed=39.31s tid=0x0000000100000000 nid=24323 waiting on condition [0x...]'
        result = parser.parse_thread_header(line)

        assert result is not None
        assert result['name'] == 'Reference Handler'
        assert result['nid'] == '0x5f03'  # Decimal 24323 converted to hex
        assert result['cpu_time'] == '0.07ms'

    def test_parse_simplified_thread_with_hex_nid(self):
        parser = Java21Parser()
        line = '"Attach Listener" #14 daemon prio=9 os_prio=31 tid=0x0000000100000000 nid=0x123 waiting on condition [0x...]'
        result = parser.parse_thread_header(line)

        assert result is not None
        assert result['name'] == 'Attach Listener'
        assert result['nid'] == '0x123'

    def test_parse_gc_thread_java21(self):
        parser = Java21Parser()
        line = '"GC Thread#0" os_prio=31 cpu=0.02ms elapsed=39.32s tid=0x0000000100000000 nid=0x123 runnable'
        result = parser.parse_thread_header(line)

        assert result is not None
        assert result['name'] == 'GC Thread#0'


class TestJava25Parser:
    """Test Java 25 parser (should behave like Java 21)."""

    def test_java25_is_same_as_java21(self):
        parser21 = Java21Parser()
        parser25 = Java25Parser()

        line = '"Reference Handler" #9 [24323] daemon prio=10 os_prio=31 tid=0x0000000100000000 nid=24323 waiting on condition'

        result21 = parser21.parse_thread_header(line)
        result25 = parser25.parse_thread_header(line)

        assert result21 == result25
