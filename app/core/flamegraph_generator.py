"""Generate flamegraph SVG from collapsed stack data."""

from pathlib import Path
from app.core.stackcollapse_jstack import collapse_jstack


def generate_flamegraph_svg_file(collapsed_lines: list, output_path: str) -> str:
    """
    Generate flamegraph SVG file from collapsed stack lines.

    Args:
        collapsed_lines: List of collapsed stack lines (format: "stack;path count")
        output_path: Where to save the SVG file

    Returns:
        Path to the generated SVG file
    """
    from app.core.flamegraph_pl import FlamegraphPL

    # Create flamegraph generator
    fg = FlamegraphPL(
        title="Thread Dump Flame Graph",
        colors="hot",
        countname="threads",
        nametype="Function:",
        inverted=True,  # icicle graph mode (top to bottom)
    )

    # Parse collapsed input
    fg.parse_input(collapsed_lines)

    # Generate SVG
    svg_content = fg.generate_svg()

    # Save SVG to file
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, 'w') as f:
        f.write(svg_content)

    return str(output_file)


def generate_flamegraph_svg_from_content(content: str, output_path: str | None = None) -> str:
    """
    Generate flamegraph SVG from thread dump content.

    This function:
    1. Collapses the thread dump using stackcollapse_jstack.py
    2. Generates SVG flamegraph using flamegraph_pl.py
    3. Optionally saves the SVG to a file

    Args:
        content: Thread dump content
        output_path: Where to save the SVG file (optional, if None returns SVG content only)

    Returns:
        SVG content as string
    """
    # Step 1: Collapse stacks (include thread names for proper root frames)
    collapsed = collapse_jstack(content, include_thread_name=True)
    collapsed_lines = [f"{stack} {count}" for stack, count in collapsed.items()]

    # Step 2: Generate SVG content
    from app.core.flamegraph_pl import FlamegraphPL

    fg = FlamegraphPL(
        title="Thread Dump Flame Graph",
        colors="hot",
        countname="threads",
        nametype="Function:",
        inverted=True,
    )

    fg.parse_input(collapsed_lines)
    svg_content = fg.generate_svg()

    # Step 3: Optionally save to file
    if output_path:
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, 'w') as f:
            f.write(svg_content)

    return svg_content
