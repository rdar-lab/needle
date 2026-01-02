"""Tests for parser factory and wrapper classes."""

import pytest
from app.core.parser import (
    BaseThreadDumpParser,
    Java8Parser,
    Java11Parser,
    Java21Parser,
    Java25Parser,
    ThreadDumpParser,
    create_parser,
)


class TestCreateParser:
    """Test parser factory function."""

    def test_create_java8_parser(self):
        content = 'Full thread dump Java HotSpot(TM) 64-Bit Server VM (25.201-b09 mixed mode):'
        parser = create_parser(content)
        assert isinstance(parser, Java8Parser)

    def test_create_java11_parser(self):
        content = """
Full thread dump OpenJDK 64-Bit Server VM (11.0.27+6-LTS mixed mode, sharing):

Threads class SMR info:
        """
        parser = create_parser(content)
        assert isinstance(parser, Java11Parser)

    def test_create_java17_parser(self):
        content = """
Full thread dump OpenJDK 64-Bit Server VM (17.0.7+7 mixed mode, sharing):

Threads class SMR info:
        """
        parser = create_parser(content)
        assert isinstance(parser, Java11Parser)

    def test_create_java21_parser(self):
        content = """
Full thread dump OpenJDK 64-Bit Server VM (21.0.8+9 mixed mode, sharing):

Threads class SMR info:
        """
        parser = create_parser(content)
        assert isinstance(parser, Java21Parser)

    def test_create_java25_parser(self):
        content = """
Full thread dump OpenJDK 64-Bit Server VM (25.452-b09 mixed mode, sharing):

Threads class SMR info:
        """
        parser = create_parser(content)
        assert isinstance(parser, Java25Parser)


class TestThreadDumpParserWrapper:
    """Test backward compatibility wrapper."""

    def test_parse_with_constructor_content(self):
        content = '''
Full thread dump Java HotSpot(TM) 64-Bit Server VM (25.201-b09 mixed mode):
"Reference Handler" #2 daemon prio=10 os_prio=31 tid=0x0000000100000000 nid=0x123 runnable
   java.lang.Thread.State: RUNNABLE
	at java.lang.Object.wait0(Native Method)
'''
        parser = ThreadDumpParser(content)
        threads, deadlocks = parser.parse()

        assert len(threads) == 1
        assert threads[0].name == 'Reference Handler'
        assert threads[0].state == 'RUNNABLE'

    def test_parse_with_method_content(self):
        content = '''
Full thread dump Java HotSpot(TM) 64-Bit Server VM (25.201-b09 mixed mode):
"main" #1 prio=5 os_prio=31 tid=0x0000000100000000 nid=0x123 runnable
   java.lang.Thread.State: RUNNABLE
	at com.example.Main.main(Main.java:10)
'''
        parser = ThreadDumpParser()
        threads, deadlocks = parser.parse(content)

        assert len(threads) == 1
        assert threads[0].name == 'main'

    def test_parse_without_content_raises_error(self):
        parser = ThreadDumpParser()

        with pytest.raises(ValueError, match='No content provided'):
            parser.parse()
