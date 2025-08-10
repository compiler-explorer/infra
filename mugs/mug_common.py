from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

import cairosvg
from PIL import Image, ImageDraw, ImageFont

# Common color constants
BG_COLOR = "transparent"
TEXT_COLOR = "#000000"
CE_GREEN = "#67c52a"
BORDER_COLOR = "#333333"
HEADER_BG = "#f0f0f0"

# Common font and layout constants
FONT_FAMILY = "DejaVu Sans Mono"

# Font size constants
MINIMUM_READABLE_FONT_SIZE = 28  # Minimum font size for any text
DEFAULT_FOOTER_REDUCTION = 8  # Footer font is text_size - this value

# Layout spacing constants
DEFAULT_MARGIN = 40  # Default margin around content
CONTINUATION_LINE_SPACING = 0.84  # Spacing multiplier for continuation rows with empty labels
TABLE_CELL_PADDING = 8  # Horizontal padding inside main table cells
INFO_TABLE_HORIZONTAL_PADDING = 12  # Horizontal padding for info table
TITLE_BOTTOM_SPACING = 50  # Space after title
TABLE_TO_INFO_SPACING = 50  # Space between main table and info table
INFO_TO_FOOTER_SPACING = 40  # Space between info table and footer
INFO_TABLE_ROW_HEIGHT = 50  # Row height for info table

# Table row labels
ROW_LABEL_FUNCTION = "func()"
ROW_LABEL_MEMBER = "obj.f()"

# Column widths (original vertical table)
COL1_WIDTH = 200
COL2_WIDTH = 375
COL3_WIDTH = 375

# New horizontal table widths (for register names as headers)
REGISTER_COL_WIDTH = 120  # Width for each register column

# Layout constants
TABLE_Y = 150


def svg_to_png(svg_path: str, png_path: str = None, dpi: int = 300) -> str:
    """Convert SVG to PNG using cairosvg."""
    if png_path is None:
        png_path = svg_path.replace(".svg", ".png")

    try:
        # Read the SVG file and convert to PNG with specified DPI
        cairosvg.svg2png(url=svg_path, write_to=png_path, dpi=dpi)

        return png_path
    except Exception as e:
        raise RuntimeError(f"Failed to convert SVG to PNG: {e}") from e


def render_info_items(
    info_items: list[tuple[str, list[tuple[str, bool]]]],
    table_x: int,
    info_y: int,
    font_family: str,
    text_size: int,
    text_color: str,
    ce_green: str,
) -> tuple[str, int]:
    """Render info items with register highlighting using tspan elements."""
    svg = ""
    current_y = info_y

    for label, parts in info_items:
        svg += f"""  <text x="{table_x}" y="{current_y}" font-family="{font_family}" font-size="{text_size}">
    <tspan font-weight="bold" fill="{text_color}">{label}</tspan>"""
        for i, (text, is_register) in enumerate(parts):
            if is_register:
                dx_attr = ' dx="8"' if i == 0 else ""
                svg += f"""<tspan font-weight="bold" fill="{ce_green}"{dx_attr}>{text}</tspan>"""
            else:
                dx_attr = ' dx="8"' if i == 0 else ""
                svg += f"""<tspan fill="{text_color}"{dx_attr}>{text}</tspan>"""
        svg += """
  </text>
"""
        current_y += 28

    return svg, current_y


@dataclass
class TextMeasurement:
    width: float
    height: float
    ascent: float = 0.0
    descent: float = 0.0


@dataclass
class ContentBlock:
    content: str
    font_size: int
    font_weight: str = "normal"
    color: str = TEXT_COLOR
    font_family: str = FONT_FAMILY


@dataclass
class TableRow:
    cells: List[str]


@dataclass
class InfoItem:
    label: str
    parts: List[Tuple[str, bool]]


@dataclass
class MugLayout:
    title: str
    code_examples: List[str]
    table_headers: List[str]
    table_rows: List[TableRow]
    info_items: List[Tuple[str, str]]  # Now (label, content) pairs for info table
    footer_lines: List[str]  # Changed from footer_note to array of lines
    title_size: int
    header_size: int
    text_size: int
    info_text_size: int
    row_height: int
    footer_spacing: int

    def __post_init__(self):
        self.measurements: Dict[str, Any] = {}


class PILTextMeasurer:
    """Text measurer using PIL ImageDraw for accurate pixel measurements."""

    def __init__(self):
        self._font_cache = {}

    def _get_font(self, font_size: int, font_family: str = FONT_FAMILY):
        """Get or create a PIL font object."""
        cache_key = (font_size, font_family)
        if cache_key not in self._font_cache:
            if font_family == "DejaVu Sans Mono":
                # Common paths for DejaVu Sans Mono
                font_paths = [
                    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
                    "/System/Library/Fonts/Menlo.ttc",  # macOS
                    "C:/Windows/Fonts/consola.ttf",  # Windows
                ]
                font = None
                for path in font_paths:
                    try:
                        font = ImageFont.truetype(path, font_size)
                        break
                    except (OSError, IOError):
                        continue

                if font is None:
                    raise RuntimeError(f"Could not find DejaVu Sans Mono font in any of: {font_paths}")

                self._font_cache[cache_key] = font
            else:
                raise ValueError(f"Unsupported font family: {font_family}")

        return self._font_cache[cache_key]

    def measure_text(
        self, text: str, font_size: int, font_family: str = FONT_FAMILY, font_weight: str = "normal"
    ) -> TextMeasurement:
        font = self._get_font(font_size, font_family)

        # Create a dummy image to get text dimensions
        dummy_img = Image.new("RGB", (1, 1))
        draw = ImageDraw.Draw(dummy_img)

        # Use getbbox for more accurate measurements
        bbox = draw.textbbox((0, 0), text, font=font)
        width = bbox[2] - bbox[0]
        height = bbox[3] - bbox[1]

        # Get font metrics for ascent/descent
        ascent, descent = font.getmetrics()

        return TextMeasurement(width=float(width), height=float(height), ascent=float(ascent), descent=float(descent))

    def cleanup(self):
        """Cleanup method for compatibility with LayoutEngine."""
        # PIL doesn't need explicit cleanup like matplotlib
        pass


class LayoutEngine:
    def __init__(self, canvas_width: int, canvas_height: int, margin: int = DEFAULT_MARGIN):
        self.canvas_width = canvas_width
        self.canvas_height = canvas_height
        self.margin = margin
        self.measurer = PILTextMeasurer()

    def layout_mug(self, layout: MugLayout) -> Dict[str, Any]:
        # Measure title for horizontal placement at top
        title_measurement = self.measurer.measure_text(layout.title, layout.title_size, font_weight="bold")
        title_height_needed = title_measurement.height + TITLE_BOTTOM_SPACING

        # Use full canvas width and start content below title
        content_x = 0
        content_width = self.canvas_width
        content_y = title_height_needed

        # Calculate positions
        positions = {}
        current_y = content_y

        # Title (horizontal at top)
        positions["title"] = {
            "x": self.canvas_width // 2,  # Center horizontally
            "y": title_measurement.height,  # Position from top
            "size": layout.title_size,
            "measurement": title_measurement,
        }

        # Skip code examples - no longer needed
        positions["code_examples"] = {}

        # Table - horizontal layout with registers as headers
        table_y = current_y
        num_registers = len(layout.table_headers)  # Should be register names now

        # Find maximum font size that fits in columns
        # Start with desired size and work down until everything fits
        max_table_font_size = 60  # Start high
        min_table_font_size = 32  # Never go below this

        table_font_size = max_table_font_size
        while table_font_size >= min_table_font_size:
            # Measure the row labels at this font size
            function_measurement = self.measurer.measure_text(ROW_LABEL_FUNCTION, table_font_size)
            member_measurement = self.measurer.measure_text(ROW_LABEL_MEMBER, table_font_size)
            label_width = int(max(function_measurement.width, member_measurement.width) + TABLE_CELL_PADDING * 2)

            # Calculate column width for register columns
            table_width = content_width
            register_col_width = (table_width - label_width) // num_registers

            # Check if all table content fits at this size
            all_fits = True

            # Check headers (they use header_size not table_font_size)
            for header in layout.table_headers:
                measurement = self.measurer.measure_text(header, layout.header_size)
                if measurement.width + TABLE_CELL_PADDING * 2 > register_col_width:
                    all_fits = False
                    break

            # Check all cell content
            if all_fits:
                for row in layout.table_rows:
                    for cell in row.cells:
                        measurement = self.measurer.measure_text(cell, table_font_size)
                        if measurement.width + TABLE_CELL_PADDING * 2 > register_col_width:
                            all_fits = False
                            break
                    if not all_fits:
                        break

            if all_fits:
                # This size works!
                break
            else:
                # Try smaller
                table_font_size = int(table_font_size - 0.5)

        # Check if we couldn't find a valid size
        if not all_fits:
            raise ValueError(
                f"Cannot fit table content with minimum font size of {min_table_font_size}pt. Content is too wide for the available space."
            )

        positions["table"] = {
            "x": content_x,
            "y": table_y,
            "width": table_width,
            "col_width": register_col_width,
            "label_width": label_width,
            "num_cols": num_registers,
            "num_rows": len(layout.table_rows),  # Should be 2 now (function + member)
            "row_height": layout.row_height,
            "header_size": max(layout.header_size, table_font_size),  # Use calculated size
            "text_size": table_font_size,  # Use calculated maximum size
        }

        # Table is much shorter now: header + 2 data rows
        current_y = table_y + layout.row_height * (2 + 1) + TABLE_TO_INFO_SPACING

        # Calculate info table dimensions
        info_table_row_height = INFO_TABLE_ROW_HEIGHT

        # Calculate actual info table height accounting for empty label spacing
        # This mirrors the spacing logic in create_info_table
        actual_height = 0
        for i in range(len(layout.info_items)):
            if i < len(layout.info_items) - 1:  # Not the last row
                next_label, _ = layout.info_items[i + 1]
                if next_label.strip() == "":
                    # Next row is continuation - use reduced spacing
                    actual_height += int(info_table_row_height * CONTINUATION_LINE_SPACING)
                else:
                    # Next row is normal - use full spacing
                    actual_height += info_table_row_height
            # Note: no spacing added after the last row
        info_table_height = actual_height

        # Calculate actual info table width by measuring content
        # Find the widest label
        max_label_width = 0
        for label, _ in layout.info_items:
            if label.strip():  # Only measure non-empty labels
                measurement = self.measurer.measure_text(label, layout.info_text_size, font_weight="bold")
                max_label_width = max(max_label_width, int(measurement.width))

        # Find the widest content
        max_content_width = 0
        for _, content in layout.info_items:
            # Measure content without register highlighting for width calculation
            measurement = self.measurer.measure_text(content, layout.info_text_size)
            max_content_width = max(max_content_width, int(measurement.width))

        # Calculate actual table width
        info_label_width = max_label_width + INFO_TABLE_HORIZONTAL_PADDING * 2
        info_content_width = max_content_width + INFO_TABLE_HORIZONTAL_PADDING * 2
        actual_info_table_width = info_label_width + info_content_width

        # Center the info table
        info_table_x = (self.canvas_width - actual_info_table_width) // 2

        # Info table position and dimensions
        positions["info_items"] = {
            "x": info_table_x,
            "y": current_y,
            "width": actual_info_table_width,
            "height": info_table_height,
            "row_height": info_table_row_height,
            "text_size": layout.info_text_size,
        }

        current_y += info_table_height

        current_y += layout.footer_spacing

        # Footer lines - measure each line and find widest to scale font size
        if layout.footer_lines:
            # Start with desired size and find maximum that fits
            max_footer_font_size = layout.text_size - DEFAULT_FOOTER_REDUCTION
            min_footer_font_size = MINIMUM_READABLE_FONT_SIZE

            footer_size = max_footer_font_size
            line_measurements: List[TextMeasurement] = []
            while footer_size >= min_footer_font_size:
                # Measure all lines at this size
                max_width = 0
                line_measurements = []
                for line in layout.footer_lines:
                    measurement = self.measurer.measure_text(line, footer_size)
                    line_measurements.append(measurement)
                    max_width = max(max_width, int(measurement.width))

                # Check if widest line fits in available width
                if max_width <= content_width:
                    break
                footer_size = int(footer_size - 1)

            # Calculate total height needed for all lines
            line_height = footer_size * 1.2  # Standard line spacing

            # Position from bottom of canvas upwards accounting for descenders
            # The last line baseline should be positioned so descenders don't go below canvas
            sample_measurement = (
                line_measurements[0] if line_measurements else self.measurer.measure_text("Sample", footer_size)
            )
            last_line_baseline_y = self.canvas_height - sample_measurement.descent
            footer_start_y = last_line_baseline_y - ((len(layout.footer_lines) - 1) * line_height)

            positions["footer"] = {
                "x": self.canvas_width // 2,  # Center horizontally
                "y": footer_start_y,
                "size": footer_size,
                "line_height": line_height,
                "lines": layout.footer_lines,
                "measurements": line_measurements,
            }
        else:
            positions["footer"] = {
                "x": content_x,
                "y": current_y,
                "size": MINIMUM_READABLE_FONT_SIZE,
                "line_height": MINIMUM_READABLE_FONT_SIZE * 1.2,
                "lines": [],
                "measurements": [],
            }

        return positions

    def cleanup(self):
        self.measurer.cleanup()


def create_table_row(
    i: int,
    reg: str,
    free_func: str,
    member_func: str,
    table_x: int,
    y: int,
    table_width: int,
    row_height: int,
    col1_width: int,
    col2_width: int,
    font_family: str,
    text_size: int,
    text_color: str,
    ce_green: str,
    border_color: str,
) -> str:
    """Create a single table row with alternating background colors."""
    # Row background (alternate colors)
    row_bg = "#ffffff" if i % 2 == 0 else "#f9f9f9"
    svg = f"""  <rect x="{table_x}" y="{y}" width="{table_width}" height="{row_height}"
        fill="{row_bg}" stroke="{border_color}" stroke-width="1"/>
"""

    # Calculate vertical center position
    text_y = y + row_height // 2 + text_size // 3  # Rough vertical centering

    # Register name (with CE green accent)
    svg += f"""  <text x="{table_x + TABLE_CELL_PADDING}" y="{text_y}" font-family="{font_family}"
        font-size="{text_size}" font-weight="bold" fill="{ce_green}">{reg}</text>
"""

    # Free function parameter
    svg += f"""  <text x="{table_x + col1_width + TABLE_CELL_PADDING}" y="{text_y}" font-family="{font_family}"
        font-size="{text_size}" fill="{text_color}">{free_func}</text>
"""

    # Member function parameter
    if member_func == "this pointer":
        svg += f"""  <text x="{table_x + col1_width + col2_width + TABLE_CELL_PADDING}" y="{text_y}" font-family="{font_family}"
        font-size="{text_size}" font-weight="bold" fill="{ce_green}">{member_func}</text>
"""
    else:
        svg += f"""  <text x="{table_x + col1_width + col2_width + TABLE_CELL_PADDING}" y="{text_y}" font-family="{font_family}"
        font-size="{text_size}" fill="{text_color}">{member_func}</text>
"""

    return svg


def create_horizontal_table(
    headers: List[str],
    rows: List[List[str]],
    row_labels: List[str],  # Add row labels parameter
    table_x: int,
    table_y: int,
    col_width: int,
    row_height: int,
    label_width: int,  # Width for row labels column
    font_family: str,
    header_size: int,
    text_size: int,
    text_color: str,
    ce_green: str,
    border_color: str,
    header_bg: str,
) -> str:
    """Create a horizontal table with register names as headers and row labels."""
    table_width = len(headers) * col_width + label_width

    svg = ""

    # Header row background (including label column)
    svg += f"""  <rect x="{table_x}" y="{table_y}" width="{table_width}" height="{row_height}"
        fill="{header_bg}" stroke="{border_color}" stroke-width="1"/>
"""

    # Header text (register names) - centered in each column
    for i, header in enumerate(headers):
        x_pos = table_x + label_width + i * col_width + col_width // 2  # Center position
        y_pos = table_y + row_height // 2 + header_size // 3
        svg += f"""  <text x="{x_pos}" y="{y_pos}" font-family="{font_family}"
        font-size="{header_size}" font-weight="bold" fill="{ce_green}" text-anchor="middle">{header}</text>
"""

    # Data rows
    for row_idx, row_data in enumerate(rows):
        y = table_y + (row_idx + 1) * row_height
        row_bg = "#ffffff" if row_idx % 2 == 0 else "#f9f9f9"

        # Row background (including label column)
        svg += f"""  <rect x="{table_x}" y="{y}" width="{table_width}" height="{row_height}"
        fill="{row_bg}" stroke="{border_color}" stroke-width="1"/>
"""

        # Row label (function/member)
        label_x = table_x + label_width // 2  # Center in label column
        label_y = y + row_height // 2 + text_size // 3
        svg += f"""  <text x="{label_x}" y="{label_y}" font-family="{font_family}"
        font-size="{text_size}" font-weight="bold" fill="{text_color}" text-anchor="middle">{row_labels[row_idx]}</text>
"""

        # Row data - centered in each column
        for col_idx, cell_data in enumerate(row_data):
            x_pos = table_x + label_width + col_idx * col_width + col_width // 2  # Center position
            y_pos = y + row_height // 2 + text_size // 3

            # Highlight "this" in green
            if cell_data == "this":
                svg += f"""  <text x="{x_pos}" y="{y_pos}" font-family="{font_family}"
        font-size="{text_size}" font-weight="bold" fill="{ce_green}" text-anchor="middle">{cell_data}</text>
"""
            else:
                svg += f"""  <text x="{x_pos}" y="{y_pos}" font-family="{font_family}"
        font-size="{text_size}" fill="{text_color}" text-anchor="middle">{cell_data}</text>
"""

    return svg


def create_info_table(
    rows: List[Tuple[str, str]],  # (label, content) pairs
    table_x: int,
    table_y: int,
    table_width: int,
    row_height: int,
    font_family: str,
    text_size: int,
    text_color: str,
    ce_green: str,
    border_color: str,
    header_bg: str,
    measurer: PILTextMeasurer,
) -> str:
    """Create a 2-column info table with register highlighting."""
    # Measure each label to find the widest one
    max_label_width = 0
    for label, _ in rows:
        measurement = measurer.measure_text(label, text_size, font_weight="bold")
        max_label_width = max(max_label_width, int(measurement.width))

    # Add horizontal padding to the measured width
    label_width = int(max_label_width + INFO_TABLE_HORIZONTAL_PADDING * 2)

    svg = ""

    current_y = table_y

    for row_idx, (label, content) in enumerate(rows):
        y = current_y

        # No row background or borders for info table"""

        # Label (left column) - only if not empty
        if label.strip():
            label_x = table_x + INFO_TABLE_HORIZONTAL_PADDING
            label_y = y + row_height // 2 + text_size // 3
            svg += f"""  <text x="{label_x}" y="{label_y}" font-family="{font_family}"
        font-size="{text_size}" font-weight="bold" fill="{text_color}">{label}</text>
"""

        # Content (right column) with register highlighting
        content_x = table_x + label_width + INFO_TABLE_HORIZONTAL_PADDING
        content_y = y + row_height // 2 + text_size // 3

        # Parse content for register highlighting
        svg += f"""  <text x="{content_x}" y="{content_y}" font-family="{font_family}" font-size="{text_size}">
"""

        # Register highlighting with single regex
        import re

        # Find all registers with one regex
        register_pattern = r"\b(RAX|RBX|RCX|RDX|RSI|RDI|RBP|RSP|R\d+|XMM\d+|X\d+|V\d+|SP)\b|(XMM#)"

        last_end = 0
        for match in re.finditer(register_pattern, content):
            # Add text before the register
            if match.start() > last_end:
                svg += f"""<tspan fill="{text_color}">{content[last_end : match.start()]}</tspan>"""

            # Add the register in green
            svg += f"""<tspan font-weight="bold" fill="{ce_green}">{match.group()}</tspan>"""
            last_end = match.end()

        # Add any remaining text after the last register
        if last_end < len(content):
            svg += f"""<tspan fill="{text_color}">{content[last_end:]}</tspan>"""

        svg += """
  </text>
"""

        # Move down by appropriate spacing for next row - look ahead
        if row_idx < len(rows) - 1:  # Not the last row
            next_label, _ = rows[row_idx + 1]
            if next_label.strip() == "":
                # Next row is continuation - use less spacing
                current_y += int(row_height * CONTINUATION_LINE_SPACING)
            else:
                # Next row is normal - use full spacing
                current_y += row_height

    return svg


def wrap_text(
    text: str,
    max_width: int,
    measurer: PILTextMeasurer,
    font_size: int,
    font_family: str = FONT_FAMILY,
    font_weight: str = "normal",
) -> List[str]:
    """Wrap text to fit within max_width, breaking at word boundaries."""
    words = text.split()
    lines = []
    current_line = ""

    for word in words:
        # Try adding this word to current line
        test_line = current_line + (" " if current_line else "") + word
        measurement = measurer.measure_text(test_line, font_size, font_family, font_weight)

        if measurement.width <= max_width:
            # Word fits, add it to current line
            current_line = test_line
        else:
            # Word doesn't fit, start new line
            if current_line:
                lines.append(current_line)
            current_line = word

    # Add final line if not empty
    if current_line:
        lines.append(current_line)

    return lines
