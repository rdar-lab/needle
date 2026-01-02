"""
Python implementation of stackcollapse-jstack.pl

Collapses Java thread dumps into single lines with semicolon-separated
stack frames and occurrence counts.

This implementation closely follows the original perl script logic.
"""

import re
import sys
from typing import Dict, List, Optional


def collapse_jstack(content: str, include_thread_name: bool = True, include_tid: bool = False,
                    shorten_pkgs: bool = False) -> Dict[str, int]:
    """
    Collapse Java thread dump stacks into flamegraph format.

    This function processes jstack output and produces collapsed stacks in the format:
    "thread_name;frame1;frame2;frame3 count"

    Args:
        content: Thread dump content as string
        include_thread_name: Include thread names in collapsed stacks (default: True)
        include_tid: Include thread IDs in thread names (default: False)
        shorten_pkgs: Shorten package names to single letters (default: False)

    Returns:
        Dictionary mapping collapsed stacks to occurrence counts
    """
    collapsed: Dict[str, int] = {}
    stack: List[str] = []
    tname: Optional[str] = None
    state: str = "?"

    # Compile regex patterns
    thread_header_pattern = re.compile(r'^"([^"]*)"')
    state_pattern = re.compile(r'java\.lang\.Thread\.State:\s+(\S+)')
    frame_pattern = re.compile(r'^\s*at\s+([^\(]+)')
    timestamp_prefix_pattern = re.compile(
        r'^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:[.,]\d{3})?(?:Z|[+-]\d{2}:?\d{2})?\s+\[\d+\]\s*)'
    )

    lines = content.split('\n')
    for line in lines:
        # Strip timestamp prefix if present
        line = timestamp_prefix_pattern.sub('', line)

        # Skip comment lines
        if line.startswith('#'):
            continue

        # Check for empty line (end of current thread)
        if not line.strip():
            # Save stack
            if tname is not None:
                stack.insert(0, tname)
            if stack:
                collapsed_stack = ";".join(stack)
                collapsed[collapsed_stack] = collapsed.get(collapsed_stack, 0) + 1
            # Clear state
            stack = []
            tname = None
            state = "?"
            continue

        # Check for thread header
        match = thread_header_pattern.match(line)
        if match:
            name = match.group(1)

            if include_thread_name:
                tname = name
                if not include_tid:
                    # Remove trailing -123 suffix (e.g., "pool-1-thread-123" -> "pool-1-thread")
                    tname = re.sub(r'-\d+$', '', tname)
                    # Remove #123 suffix (e.g., "G1 Conc#0" -> "G1 Conc", "GC Thread#32" -> "GC Thread", "GC task thread#0" -> "GC task thread")
                    tname = re.sub(r'#\d+', '', tname)
                    # Remove trailing digits from CompilerThread (e.g., "C2 CompilerThread0" -> "C2 CompilerThread")
                    tname = re.sub(r'(CompilerThread)\d+$', r'\1', tname)

            # Detect background threads
            if re.search(r'C\..*CompilerThread', name):
                state = "BACKGROUND"
            if re.search(r'Signal Dispatcher', name):
                state = "BACKGROUND"
            if re.search(r'Service Thread', name):
                state = "BACKGROUND"
            if re.search(r'Attach Listener', name):
                state = "BACKGROUND"
            continue

        # Check for thread state
        match = state_pattern.search(line)
        if match and state == "?":
            state = match.group(1)
            continue

        # Check for stack frame
        match = frame_pattern.match(line)
        if match:
            func = match.group(1)

            # Shorten packages if requested
            if shorten_pkgs:
                pkg_match = re.match(r'(.*\.)([^.]+\.[^.]+)$', func)
                if pkg_match:
                    pkgs, cls_func = pkg_match.groups()
                    pkgs = re.sub(r'(\w)\w*', r'\1', pkgs)
                    func = pkgs + cls_func

            # Add to front of stack (unshift behavior)
            stack.insert(0, func)

            # Fix state for epollWait
            if 'epollWait' in func or 'EPoll.wait' in func:
                state = "WAITING"
            # Fix state for networking functions
            if 'socketAccept$' in func or 'Socket.*accept0$' in func or 'socketRead0$' in func:
                state = "NETWORK"
            continue

        # Skip info lines
        if line.strip().startswith('-') or re.match(r'^2\d\d\d-', line) or \
           'Full thread dump' in line or 'JNI global references:' in line:
            continue

    # Sort and output
    return collapsed


class ThreadStackCollapser:
    """
    Wrapper class for backward compatibility.

    This class provides the same interface as before but now uses the
    direct parsing implementation.
    """

    def __init__(self, include_thread_name: bool = True, include_tid: bool = False, shorten_pkgs: bool = False):
        self.include_thread_name = include_thread_name
        self.include_tid = include_tid
        self.shorten_pkgs = shorten_pkgs
        self.collapsed: Dict[str, int] = {}

    def parse_thread_dump(self, content: str) -> Dict[str, int]:
        """Parse thread dump and collapse stacks."""
        self.collapsed = collapse_jstack(
            content,
            include_thread_name=self.include_thread_name,
            include_tid=self.include_tid,
            shorten_pkgs=self.shorten_pkgs
        )
        return self.collapsed

    def get_output(self) -> List[str]:
        """Get collapsed stacks as list of strings."""
        output = []
        for stack in sorted(self.collapsed.keys()):
            # Only output non-empty stacks
            if stack:
                output.append(f"{stack} {self.collapsed[stack]}")
        return output


def collapse_threads_from_parsed(threads, include_thread_name: bool = True) -> Dict[str, int]:
    """
    Collapse already-parsed ThreadInfo objects (for backward compatibility).

    This is a convenience function that works with already-parsed threads.
    For new code, use collapse_jstack() directly on raw content instead.

    Args:
        threads: List of ThreadInfo objects
        include_thread_name: If True, include thread name as root (default: True)

    Returns:
        Dictionary mapping collapsed stack to occurrence count
    """
    collapsed = {}

    for thread in threads:
        parts = []

        # Process stack trace
        for frame in thread.stack_trace:
            # Clean frame (remove "at " and file:line)
            if frame.startswith("at "):
                frame = frame[3:]
            if "(" in frame:
                frame = frame[:frame.index("(")]
            parts.append(frame.strip())

        # Reverse to root->leaf order
        parts.reverse()

        # Add thread name at the beginning
        if include_thread_name:
            thread_name = thread.name
            parts.insert(0, thread_name)

        # Create collapsed stack
        collapsed_stack = ";".join(parts)
        collapsed[collapsed_stack] = collapsed.get(collapsed_stack, 0) + 1

    return collapsed


# Alias for backward compatibility
collapse_threads = collapse_threads_from_parsed


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python stackcollapse_jstack.py <input_file>", file=sys.stderr)
        print("       python stackcollapse_jstack.py <input_file> --no-thread-name", file=sys.stderr)
        print("       python stackcollapse_jstack.py <input_file> --shorten-pkgs", file=sys.stderr)
        sys.exit(1)

    input_file = sys.argv[1]
    include_thread_name = "--no-thread-name" not in sys.argv
    shorten_pkgs = "--shorten-pkgs" in sys.argv

    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Collapse stacks directly from content
        collapsed = collapse_jstack(
            content,
            include_thread_name=include_thread_name,
            shorten_pkgs=shorten_pkgs
        )

        # Output in flamegraph format
        for stack in sorted(collapsed.keys()):
            # Only output non-empty stacks
            if stack:
                print(f"{stack} {collapsed[stack]}")

    except FileNotFoundError:
        print(f"Error: File not found: {input_file}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
