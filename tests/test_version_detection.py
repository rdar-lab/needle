"""Tests for Java version detection from thread dumps."""

import pytest
from app.core.parser import (
    detect_java_version,
    extract_java_version_string,
    extract_timestamp,
)


class TestVersionDetection:
    """Test Java version detection logic."""

    def test_detect_java_8_no_smr(self):
        """Java 8 does not have SMR section."""
        content = """
Full thread dump Java HotSpot(TM) 64-Bit Server VM (25.201-b09 mixed mode):
"Reference Handler" #2 daemon prio=10 os_prio=31 runnable
        """
        assert detect_java_version(content) == 8

    def test_detect_java_11_with_smr(self):
        """Java 11+ has SMR section."""
        content = """
Full thread dump OpenJDK 64-Bit Server VM (11.0.27+6-LTS mixed mode, sharing):

Threads class SMR info:
_java_thread_list=0x0000000100000000, length=1
        """
        assert detect_java_version(content) == 11

    def test_detect_java_17(self):
        content = """
Full thread dump OpenJDK 64-Bit Server VM (17.0.7+7 mixed mode, sharing):

Threads class SMR info:
        """
        assert detect_java_version(content) == 17

    def test_detect_java_21(self):
        content = """
Full thread dump OpenJDK 64-Bit Server VM (21.0.8+9 mixed mode, sharing):

Threads class SMR info:
        """
        assert detect_java_version(content) == 21

    def test_detect_java_25(self):
        content = """
Full thread dump OpenJDK 64-Bit Server VM (25.452-b09 mixed mode, sharing):

Threads class SMR info:
        """
        assert detect_java_version(content) == 25

    def test_detect_future_version_fallback(self):
        """Unknown future versions should return detected number."""
        content = """
Full thread dump OpenJDK 64-Bit Server VM (33.0.0+1 mixed mode, sharing):

Threads class SMR info:
        """
        assert detect_java_version(content) == 33


class TestExtractJavaVersionString:
    """Test Java version string extraction."""

    def test_extract_java11_version(self):
        content = 'Full thread dump OpenJDK 64-Bit Server VM (11.0.27+6-LTS mixed mode, sharing):'
        result = extract_java_version_string(content)
        assert result == '11.0.27+6-LTS mixed mode, sharing'

    def test_extract_java17_version(self):
        content = 'Full thread dump OpenJDK 64-Bit Server VM (17.0.7+7 mixed mode, sharing):'
        result = extract_java_version_string(content)
        assert result == '17.0.7+7 mixed mode, sharing'

    def test_extract_java8_version(self):
        content = 'Full thread dump Java HotSpot(TM) 64-Bit Server VM (25.201-b09 mixed mode):'
        result = extract_java_version_string(content)
        assert result == '25.201-b09 mixed mode'

    def test_extract_no_version(self):
        content = 'Random content without version'
        result = extract_java_version_string(content)
        assert result is None


class TestExtractTimestamp:
    """Test timestamp extraction."""

    def test_extract_iso8601_timestamp_same_line(self):
        content = '2025-11-25T14:27:11.443-0800 [190088] Full thread dump OpenJDK 64-Bit Server VM'
        result = extract_timestamp(content)
        assert result == '2025-11-25T14:27:11.443-0800'

    def test_extract_simple_timestamp_previous_line(self):
        content = """2026-01-01 19:58:06
Full thread dump OpenJDK 64-Bit Server VM"""
        result = extract_timestamp(content)
        assert result == '2026-01-01 19:58:06'

    def test_extract_no_timestamp(self):
        content = 'Full thread dump OpenJDK 64-Bit Server VM'
        result = extract_timestamp(content)
        assert result is None
