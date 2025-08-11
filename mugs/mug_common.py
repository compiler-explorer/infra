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
FONT_NAME = "DejaVuSansMono.ttf"

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

# Typography and appearance constants
LINE_HEIGHT_MULTIPLIER = 1.2  # Standard line spacing multiplier
TEXT_VERTICAL_CENTER_OFFSET = 3  # Divisor for rough vertical centering (text_size // 3)
FOOTER_OPACITY = 0.6  # Opacity for footer text
ALTERNATING_ROW_COLORS = ("#ffffff", "#f9f9f9")  # Colors for alternating table rows

# Default canvas dimensions
DEFAULT_WIDTH = 1100
DEFAULT_HEIGHT = 800
DEFAULT_DPI = 300


def svg_to_png(svg_path: str, png_path: str = None, dpi: int = DEFAULT_DPI) -> str:
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
    font_family: str = FONT_NAME


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

    def _get_font(self, font_size: int, font_family: str = FONT_NAME, font_weight: str = "normal"):
        """Get or create a PIL font object."""
        cache_key = (font_size, font_family, font_weight)
        if cache_key not in self._font_cache:
            font = ImageFont.truetype(font_family, font_size)
            self._font_cache[cache_key] = font

        return self._font_cache[cache_key]

    def measure_text(
        self, text: str, font_size: int, font_family: str = FONT_NAME, font_weight: str = "normal"
    ) -> TextMeasurement:
        font = self._get_font(font_size, font_family, font_weight)

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

    def get_svg_font_family(self, font_filename: str = FONT_NAME) -> str:
        """Get the SVG-compatible font family name from a font file."""
        # Load font and extract family name
        font = ImageFont.truetype(font_filename, 12)  # Size doesn't matter for name extraction
        family_name, _ = font.getname()
        return family_name


class LayoutEngine:
    def __init__(self, canvas_width: int, canvas_height: int, margin: int = DEFAULT_MARGIN):
        self.canvas_width = canvas_width
        self.canvas_height = canvas_height
        self.margin = margin
        self.measurer = PILTextMeasurer()
        # Cache the SVG font family name
        self._svg_font_family: str | None = None

    @property
    def svg_font_family(self) -> str:
        """Get the SVG-compatible font family name."""
        if self._svg_font_family is None:
            self._svg_font_family = self.measurer.get_svg_font_family()
        return self._svg_font_family

    def _calculate_table_font_size(self, layout: MugLayout, content_width: int) -> Tuple[int, int, int]:
        """Calculate optimal table font size and dimensions."""
        num_registers = len(layout.table_headers)
        max_table_font_size = 60
        min_table_font_size = 32

        table_font_size = max_table_font_size
        while table_font_size >= min_table_font_size:
            # Measure the row labels at this font size
            function_measurement = self.measurer.measure_text(ROW_LABEL_FUNCTION, table_font_size)
            member_measurement = self.measurer.measure_text(ROW_LABEL_MEMBER, table_font_size)
            label_width = int(max(function_measurement.width, member_measurement.width) + TABLE_CELL_PADDING * 2)

            # Calculate column width for register columns
            register_col_width = (content_width - label_width) // num_registers

            # Check if all table content fits at this size
            all_fits = True

            # Check headers
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
                return table_font_size, label_width, register_col_width

            table_font_size = int(table_font_size - 0.5)

        raise ValueError(
            f"Cannot fit table content with minimum font size of {min_table_font_size}pt. Content is too wide for the available space."
        )

    def _calculate_footer_positioning(self, layout: MugLayout, content_width: int) -> Dict[str, Any]:
        """Calculate footer font size and positioning."""
        if not layout.footer_lines:
            return {
                "x": 0,
                "y": self.canvas_height,
                "size": MINIMUM_READABLE_FONT_SIZE,
                "line_height": MINIMUM_READABLE_FONT_SIZE * LINE_HEIGHT_MULTIPLIER,
                "lines": [],
                "measurements": [],
            }

        max_footer_font_size = layout.text_size - DEFAULT_FOOTER_REDUCTION
        min_footer_font_size = MINIMUM_READABLE_FONT_SIZE

        footer_size = max_footer_font_size
        line_measurements: List[TextMeasurement] = []
        while footer_size >= min_footer_font_size:
            max_width = 0
            line_measurements = []
            for line in layout.footer_lines:
                measurement = self.measurer.measure_text(line, footer_size)
                line_measurements.append(measurement)
                max_width = max(max_width, int(measurement.width))

            if max_width <= content_width:
                break
            footer_size = int(footer_size - 1)

        # Calculate positioning from bottom upwards
        line_height = footer_size * LINE_HEIGHT_MULTIPLIER
        sample_measurement = (
            line_measurements[0] if line_measurements else self.measurer.measure_text("Sample", footer_size)
        )
        last_line_baseline_y = self.canvas_height - sample_measurement.descent
        footer_start_y = last_line_baseline_y - ((len(layout.footer_lines) - 1) * line_height)

        # Get font ascent for visual positioning
        footer_ascent = sample_measurement.ascent

        return {
            "x": self.canvas_width // 2,
            "y": footer_start_y,
            "size": footer_size,
            "line_height": line_height,
            "lines": layout.footer_lines,
            "measurements": line_measurements,
            "ascent": footer_ascent,
        }

    def _calculate_info_table_dimensions(self, layout: MugLayout) -> Tuple[int, int, int]:
        """Calculate info table dimensions and positioning."""
        # Calculate the spacing between first and last row positions
        # This matches exactly what create_info_table() does
        spacing_height = 0
        for i in range(len(layout.info_items) - 1):  # N-1 gaps between N rows
            next_label, _ = layout.info_items[i + 1]
            if next_label.strip() == "":
                spacing_height += int(INFO_TABLE_ROW_HEIGHT * CONTINUATION_LINE_SPACING)
            else:
                spacing_height += INFO_TABLE_ROW_HEIGHT

        # Total visual height: spacing + one row height for the last row's content
        actual_height = spacing_height + INFO_TABLE_ROW_HEIGHT

        # Calculate actual width by measuring content
        max_label_width = 0
        for label, _ in layout.info_items:
            if label.strip():
                measurement = self.measurer.measure_text(label, layout.info_text_size, font_weight="bold")
                max_label_width = max(max_label_width, int(measurement.width))

        max_content_width = 0
        for _, content in layout.info_items:
            measurement = self.measurer.measure_text(content, layout.info_text_size)
            max_content_width = max(max_content_width, int(measurement.width))

        info_label_width = max_label_width + INFO_TABLE_HORIZONTAL_PADDING * 2
        info_content_width = max_content_width + INFO_TABLE_HORIZONTAL_PADDING * 2
        actual_width = info_label_width + info_content_width

        return actual_height, actual_width, info_label_width

    def layout_mug(self, layout: MugLayout) -> Dict[str, Any]:
        # Measure title for horizontal placement at top
        title_measurement = self.measurer.measure_text(layout.title, layout.title_size, font_weight="bold")
        title_height_needed = title_measurement.height + TITLE_BOTTOM_SPACING

        # Use full canvas width and start content below title
        content_x = 0
        content_width = self.canvas_width
        content_y = title_height_needed

        positions = {}

        # Title (horizontal at top)
        positions["title"] = {
            "x": self.canvas_width // 2,
            "y": title_measurement.height,
            "size": layout.title_size,
            "measurement": title_measurement,
        }

        # Skip code examples - no longer needed
        positions["code_examples"] = {}

        # Table calculation
        table_y = content_y
        table_font_size, label_width, register_col_width = self._calculate_table_font_size(layout, content_width)

        positions["table"] = {
            "x": content_x,
            "y": table_y,
            "width": content_width,
            "col_width": register_col_width,
            "label_width": label_width,
            "num_cols": len(layout.table_headers),
            "num_rows": len(layout.table_rows),
            "row_height": layout.row_height,
            "header_size": max(layout.header_size, table_font_size),
            "text_size": table_font_size,
        }

        # Calculate where the main table ends
        main_table_bottom = table_y + layout.row_height * (len(layout.table_rows) + 1)  # header + data rows

        # Footer calculation
        footer_data = self._calculate_footer_positioning(layout, content_width)
        positions["footer"] = footer_data
        footer_start_y = footer_data["y"]

        # Calculate footer visual top (baseline - ascent) for proper centering
        footer_visual_top = footer_start_y - footer_data["ascent"]

        # Info table calculation
        info_table_height, actual_info_table_width, _ = self._calculate_info_table_dimensions(layout)
        info_table_y = (main_table_bottom + footer_visual_top - info_table_height) // 2
        info_table_x = (self.canvas_width - actual_info_table_width) // 2

        positions["info_items"] = {
            "x": info_table_x,
            "y": info_table_y,
            "width": actual_info_table_width,
            "height": info_table_height,
            "row_height": INFO_TABLE_ROW_HEIGHT,
            "text_size": layout.info_text_size,
        }

        return positions


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
    row_bg = ALTERNATING_ROW_COLORS[i % 2]
    svg = f"""  <rect x="{table_x}" y="{y}" width="{table_width}" height="{row_height}"
        fill="{row_bg}" stroke="{border_color}" stroke-width="1"/>
"""

    # Calculate vertical center position
    text_y = y + row_height // 2 + text_size // TEXT_VERTICAL_CENTER_OFFSET

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
        y_pos = table_y + row_height // 2 + header_size // TEXT_VERTICAL_CENTER_OFFSET
        svg += f"""  <text x="{x_pos}" y="{y_pos}" font-family="{font_family}"
        font-size="{header_size}" font-weight="bold" fill="{ce_green}" text-anchor="middle">{header}</text>
"""

    # Data rows
    for row_idx, row_data in enumerate(rows):
        y = table_y + (row_idx + 1) * row_height
        row_bg = ALTERNATING_ROW_COLORS[row_idx % 2]

        # Row background (including label column)
        svg += f"""  <rect x="{table_x}" y="{y}" width="{table_width}" height="{row_height}"
        fill="{row_bg}" stroke="{border_color}" stroke-width="1"/>
"""

        # Row label (function/member)
        label_x = table_x + label_width // 2  # Center in label column
        label_y = y + row_height // 2 + text_size // TEXT_VERTICAL_CENTER_OFFSET
        svg += f"""  <text x="{label_x}" y="{label_y}" font-family="{font_family}"
        font-size="{text_size}" font-weight="bold" fill="{text_color}" text-anchor="middle">{row_labels[row_idx]}</text>
"""

        # Row data - centered in each column
        for col_idx, cell_data in enumerate(row_data):
            x_pos = table_x + label_width + col_idx * col_width + col_width // 2  # Center position
            y_pos = y + row_height // 2 + text_size // TEXT_VERTICAL_CENTER_OFFSET

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
            label_y = y + row_height // 2 + text_size // TEXT_VERTICAL_CENTER_OFFSET
            svg += f"""  <text x="{label_x}" y="{label_y}" font-family="{font_family}"
        font-size="{text_size}" font-weight="bold" fill="{text_color}">{label}</text>
"""

        # Content (right column) with register highlighting
        content_x = table_x + label_width + INFO_TABLE_HORIZONTAL_PADDING
        content_y = y + row_height // 2 + text_size // TEXT_VERTICAL_CENTER_OFFSET

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
    font_family: str = FONT_NAME,
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
