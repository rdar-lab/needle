"""
Python implementation of flamegraph.pl

Generates interactive SVG flamegraphs from collapsed stack traces.
Input format: "func1;func2;func3 count"
Output format: Interactive SVG with zoom, search, and mouseover
"""

import re
from typing import Dict, List, Optional

from app.core.flamegraph_js import FLAMEGRAPH_JS


class FlamegraphPL:
    """Generate flamegraph SVG from collapsed stack traces."""

    def __init__(
        self,
        title: str = "Flame Graph",
        width: int = 1200,
        frame_height: int = 16,
        font_size: int = 12,
        font_type: str = "Verdana",
        colors: str = "hot",
        countname: str = "samples",
        nametype: str = "Function:",
        inverted: bool = False,
    ):
        self.title = title
        self.width = width
        self.frame_height = frame_height
        self.font_size = font_size
        self.font_type = font_type
        self.colors = colors
        self.countname = countname
        self.nametype = nametype
        self.inverted = inverted

        # Internal structures
        self.ypad1 = self.font_size * 3  # pad top, include title
        self.ypad2 = self.font_size * 2 + 10  # pad bottom, include labels
        self.xpad = 10  # pad left and right
        self.depth_max = 0

        # Node storage: "func;depth;etime" -> {stime: float}
        self.nodes: Dict[str, Dict[str, float]] = {}
        self.tmp: Dict[str, Dict[str, float]] = {}

        # Total time (sum of all samples)
        self.time_max: Optional[float] = None

    def _name_hash(self, name: str) -> float:
        """Generate hash for function name."""
        vector = 0
        weight = 1
        max_val = 1
        mod = 10

        for i, c in enumerate(name):
            char_val = ord(c) % mod
            vector += (char_val / (mod - 1)) * weight
            max_val += 1 * weight
            weight *= 0.70
            if mod > 12:
                break
            mod += 1

        return 1 - (vector / max_val)

    def _random_name_hash(self, name: str) -> float:
        """Generate consistent random hash for function name."""
        # Use built-in hash() with seeded random
        hash_val = abs(hash(name)) % (2**32)
        return (hash_val / (2**32))

    def _color(self, name: str) -> str:
        """Get color for a function frame."""
        # Generate hash values - in default mode, v1, v2, v3 all use the same name
        # This matches the perl flamegraph.pl random_namehash behavior
        v1 = self._random_name_hash(name)
        v2 = self._random_name_hash(name)
        v3 = self._random_name_hash(name)

        # Apply color theme
        if self.colors == "hot":
            r = 205 + int(50 * v3)
            g = int(230 * v1)
            b = int(55 * v2)
            return f"rgb({r},{g},{b})"
        elif self.colors == "java":
            # Java coloring - green for Java, yellow for C++, red for system
            if any(pattern in name for pattern in ["java.", "javax.", "jdk.", "org.", "com.", "net.", "io.", "sun."]):
                # Green theme for Java
                g = 200 + int(55 * v1)
                x = 50 + int(60 * v1)
                return f"rgb({x},{g},{x})"
            elif "::" in name:
                # Yellow for C++
                x = 175 + int(55 * v1)
                b = 50 + int(20 * v1)
                return f"rgb({x},{x},{b})"
            else:
                # Red for system
                r = 200 + int(55 * v1)
                x = 50 + int(80 * v1)
                return f"rgb({r},{x},{x})"
        else:
            # Default hot colors
            r = 205 + int(50 * v3)
            g = int(230 * v1)
            b = int(55 * v2)
            return f"rgb({r},{g},{b})"

    def _flow(self, last: List[str], this: List[str], value: float, delta: Optional[float] = None) -> List[str]:
        """
        Merge two stacks, storing merged frames in self.nodes.

        This is the core algorithm from flamegraph.pl that properly merges
        stack traces by finding common prefixes.
        """
        len_a = len(last) - 1
        len_b = len(this) - 1

        # Find common prefix length - handle empty arrays
        len_same = 0
        for i in range(min(len_a, len_b) + 1):
            if i <= len_a and i <= len_b and last[i] == this[i]:
                len_same = i + 1
            else:
                break

        # Process frames that are ending (from len_a down to len_same)
        for i in range(len_a, len_same - 1, -1):
            key = f"{last[i]};{i}"
            node_id = f"{key};{value}"

            if key in self.tmp:
                self.nodes[node_id] = {"stime": self.tmp[key].get("stime", 0)}
                if "delta" in self.tmp[key]:
                    self.nodes[node_id]["delta"] = self.tmp[key]["delta"]
                del self.tmp[key]

        # Process frames that are starting (from len_same to len_b)
        for i in range(len_same, len_b + 1):
            key = f"{this[i]};{i}"
            if key not in self.tmp:
                self.tmp[key] = {}
            self.tmp[key]["stime"] = value

            if delta is not None and i == len_b:
                if "delta" not in self.tmp[key]:
                    self.tmp[key]["delta"] = 0
                self.tmp[key]["delta"] += delta

        return this

    def parse_input(self, lines: List[str]):
        """
        Parse collapsed stack input and build frame tree.

        Input format: "func1;func2;func3 count"
        """
        data = []
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            # Parse "stack count"
            match = re.match(r'^(.*)\s+(\d+(?:\.\d+)?)$', line)
            if match:
                stack, count_str = match.groups()
                count = float(count_str)
                data.append((stack, count))

        # Sort by stack (alphabetically)
        data.sort(key=lambda x: x[0])

        # Process and merge frames
        last = []
        time = 0

        for stack, samples in data:
            # Split stack into frames
            frames = [""] + stack.split(";")
            this = frames

            # Merge stacks
            last = self._flow(last, this, time)
            time += samples

        # Final merge
        self._flow(last, [], time)

        self.time_max = time

        # Calculate max depth
        for node_id in self.nodes:
            parts = node_id.split(";")
            if len(parts) >= 2:
                try:
                    depth = int(parts[-2])
                    self.depth_max = max(self.depth_max, depth)
                except ValueError:
                    pass

    def _shorten_name(self, name: str, width: float) -> str:
        """Shorten function name to fit in width."""
        if not name:
            return ""

        font_width = 0.59  # avg width relative to fontsize
        max_chars = max(3, int(width / (self.font_size * font_width)))

        if len(name) <= max_chars:
            return name

        # Try to show class.method
        parts = name.split(".")
        if len(parts) > 2:
            class_method = ".".join(parts[-2:])
            if len(class_method) <= max_chars - 3:
                return "..." + class_method
            if len(class_method) <= max_chars:
                return class_method

        result = name[:max_chars]
        if len(name) > max_chars:
            result = name[:max_chars-2] + ".."
        return result

    def _escape_xml(self, text: str) -> str:
        """Escape special XML characters."""
        text = text.replace("&", "&amp;")
        text = text.replace("<", "&lt;")
        text = text.replace(">", "&gt;")
        text = text.replace('"', "&quot;")
        return text

    def generate_svg(self) -> str:
        """Generate SVG flamegraph."""
        if self.time_max is None or self.time_max == 0:
            return self._empty_svg()

        width_per_time = (self.width - 2 * self.xpad) / self.time_max

        # Calculate image height
        image_height = (self.depth_max + 1) * self.frame_height + self.ypad1 + self.ypad2

        # Build SVG
        svg_parts = []
        svg_parts.append(self._svg_header(image_height))
        svg_parts.append(self._svg_styles())
        svg_parts.append(self._svg_javascript())
        svg_parts.append(self._svg_titles())
        svg_parts.append('<g id="frames">\n')

        # Draw all frames
        for node_id in sorted(self.nodes.keys()):
            parts = node_id.split(";")
            if len(parts) < 3:
                continue

            try:
                func = ";".join(parts[:-2])
                depth = int(parts[-2])
                etime = float(parts[-1])
            except (ValueError, IndexError):
                continue

            stime = self.nodes[node_id].get("stime", 0)

            if func == "" and depth == 0:
                etime = self.time_max

            x1 = self.xpad + stime * width_per_time
            x2 = self.xpad + etime * width_per_time

            # Calculate y position (icicle graph: top to bottom)
            if not self.inverted:
                y1 = image_height - self.ypad2 - (depth + 1) * self.frame_height + 1
                y2 = image_height - self.ypad2 - depth * self.frame_height
            else:
                y1 = self.ypad1 + depth * self.frame_height
                y2 = self.ypad1 + (depth + 1) * self.frame_height - 1

            width = x2 - x1
            if width < 0.1:
                continue

            # Calculate samples and percentage
            samples = (etime - stime)
            pct = (100 * samples / self.time_max) if self.time_max > 0 else 0

            # Format title text (matching perl output format)
            if func == "" and depth == 0:
                title = f"all ({int(samples)} {self.countname}, 100%)"
            else:
                escaped_func = self._escape_xml(func)
                title = f"{escaped_func} ({int(samples)} {self.countname}, {pct:.2f}%)"

            # Get color
            if func == "--" or func == "-":
                color = "rgb(200,200,200)"
            else:
                color = self._color(func)

            # Draw frame (matching perl format exactly)
            short_name = self._shorten_name(func, width)
            escaped_name = self._escape_xml(short_name)

            # Use exact format from perl: <g >, <rect height="15.0", rx="2" ry="2"
            svg_parts.append(f'<g >\n')
            svg_parts.append(f'<title>{title}</title>')
            svg_parts.append(
                f'<rect x="{x1:.1f}" y="{int(y1)}" width="{width:.1f}" '
                f'height="15.0" fill="{color}" rx="2" ry="2" />\n'
            )

            # Add text if wide enough (narrow frames show no text for cleaner look)
            # Only show text if width is >= 30 pixels and short_name is not just ".."
            if width >= 30 and short_name and short_name != "..":
                # Calculate text y position (centered vertically in the rect)
                text_y = y1 + 11.5  # This matches the perl script's text positioning
                svg_parts.append(
                    f'<text  x="{x1+3:.2f}" y="{text_y:.1f}">{escaped_name}</text>\n'
                )
            else:
                # Empty text element for consistency
                svg_parts.append(f'<text  x="{x1+3:.2f}" y="{y1 + 11.5:.1f}"></text>\n')

            svg_parts.append(f'</g>\n')

        svg_parts.append('</g>\n')
        svg_parts.append('</svg>\n')

        return "".join(svg_parts)

    def _svg_header(self, height: int) -> str:
        """Generate SVG header."""
        return f'''<?xml version="1.0" standalone="no"?>
<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN" "http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd">
<svg version="1.1" width="{self.width}" height="{height}" onload="init(evt)" viewBox="0 0 {self.width} {height}" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">
<!-- Flame graph stack visualization. See https://github.com/brendangregg/FlameGraph for latest version, and http://www.brendangregg.com/flamegraphs.html for examples. -->
<!-- NOTES:  -->
<defs>
  <linearGradient id="background" y1="0" y2="1" x1="0" x2="0">
    <stop stop-color="#eeeeee" offset="5%"/>
    <stop stop-color="#eeeeb0" offset="95%"/>
  </linearGradient>
</defs>
'''

    def _svg_styles(self) -> str:
        """Generate SVG CSS styles."""
        return f'''<style type="text/css">
\ttext {{ font-family:{self.font_type}; font-size:{self.font_size}px; fill:rgb(0,0,0); }}
\t#search, #ignorecase {{ opacity:0.1; cursor:pointer; }}
\t#search:hover, #search.show, #ignorecase:hover, #ignorecase.show {{ opacity:1; }}
\t#subtitle {{ text-anchor:middle; font-color:rgb(160,160,160); }}
\t#title {{ text-anchor:middle; font-size:17px}}
\t#unzoom {{ cursor:pointer; }}
\t#frames > *:hover {{ stroke:black; stroke-width:0.5; cursor:pointer; }}
\t.hide {{ display:none; }}
\t.parent {{ opacity:0.5; }}
</style>
'''

    def _svg_javascript(self) -> str:
        """Generate embedded JavaScript."""
        return FLAMEGRAPH_JS

    def _svg_titles(self) -> str:
        """Generate SVG title elements."""
        return f'''<rect width="100%" height="100%" fill="url(#background)"/>
<text id="title" x="{self.width//2}" y="{self.font_size * 2}" text-anchor="middle" font-size="{self.font_size + 5}">{self._escape_xml(self.title)}</text>
<text id="details" x="10" y="{self.ypad1 + self.depth_max * self.frame_height + 20}"> </text>
<text id="unzoom" x="10" y="{self.font_size * 2}" class="hide">Reset Zoom</text>
<text id="search" x="{self.width - 10 - 100}" y="{self.font_size * 2}">Search</text>
<text id="ignorecase" x="{self.width - 10 - 26}" y="{self.font_size * 2}">ic</text>
<text id="matched" x="{self.width - 10 - 100}" y="{self.ypad1 + self.depth_max * self.frame_height + 20}"> </text>
'''

    def _empty_svg(self) -> str:
        """Generate empty SVG."""
        height = 400
        return f'''<?xml version="1.0" standalone="no"?>
<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN" "http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd">
<svg version="1.1" width="{self.width}" height="{height}" xmlns="http://www.w3.org/2000/svg">
<rect width="100%" height="100%" fill="#ffffb0"/>
<text x="50%" y="50%" text-anchor="middle" font-family="{self.font_type}" font-size="16">
No stack trace data available
</text>
</svg>'''


def generate_flamegraph_from_collapsed(collapsed_lines: List[str], **kwargs) -> str:
    """
    Convenience function to generate flamegraph from collapsed stack data.

    Args:
        collapsed_lines: List of collapsed stack strings ("func1;func2 count")
        **kwargs: Optional arguments for FlamegraphPL (title, width, colors, etc.)

    Returns:
        SVG string
    """
    fg = FlamegraphPL(**kwargs)
    fg.parse_input(collapsed_lines)
    return fg.generate_svg()
