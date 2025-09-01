"""SVG generation functions for mug layouts."""

import re

import cairosvg

from core.constants import (
    ALTERNATING_ROW_COLORS,
    CONTINUATION_LINE_SPACING,
    DEFAULT_DPI,
    INFO_ITEM_DX_SPACING,
    INFO_ITEM_LINE_SPACING,
    INFO_TABLE_HORIZONTAL_PADDING,
    SVG_STROKE_WIDTH,
    TABLE_CELL_PADDING,
    TEXT_VERTICAL_CENTER_OFFSET,
)
from core.data_structures import TableRow
from core.text_measurement import PILTextMeasurer


def svg_to_png(svg_path: str, png_path: str | None = None, dpi: int = DEFAULT_DPI) -> str:
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
                dx_attr = f' dx="{INFO_ITEM_DX_SPACING}"' if i == 0 else ""
                svg += f"""<tspan font-weight="bold" fill="{ce_green}"{dx_attr}>{text}</tspan>"""
            else:
                dx_attr = f' dx="{INFO_ITEM_DX_SPACING}"' if i == 0 else ""
                svg += f"""<tspan fill="{text_color}"{dx_attr}>{text}</tspan>"""
        svg += """
  </text>
"""
        current_y += INFO_ITEM_LINE_SPACING

    return svg, current_y


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
        fill="{row_bg}" stroke="{border_color}" stroke-width="{SVG_STROKE_WIDTH}"/>
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
    headers: list[str],
    rows: list[TableRow],
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
        fill="{header_bg}" stroke="{border_color}" stroke-width="{SVG_STROKE_WIDTH}"/>
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
        fill="{row_bg}" stroke="{border_color}" stroke-width="{SVG_STROKE_WIDTH}"/>
"""

        # Row label (function/member)
        label_x = table_x + label_width // 2  # Center in label column
        label_y = y + row_height // 2 + text_size // TEXT_VERTICAL_CENTER_OFFSET
        svg += f"""  <text x="{label_x}" y="{label_y}" font-family="{font_family}"
        font-size="{text_size}" font-weight="bold" fill="{text_color}" text-anchor="middle">{row_data.label}</text>
"""

        # Row data - centered in each column
        for col_idx, cell_data in enumerate(row_data.cells):
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
    rows: list[tuple[str, str]],  # (label, content) pairs
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
        # Find all registers with one regex
        register_pattern = r"\b([RE]?([ABCD]X|[DS]I|[BSI]P)|f?[RFXVastf]\d+|[XYZ]MM\d+|SP|FP|LR|PC|ra|sp|fp|x\d+|a[0-7]|s[0-9]|s1[01]|t[0-6]|fa[0-7]|ft[0-9]|ft1[01]|fs[0-9]|fs1[01]|S\d+|D\d+)\b|(XMM#)"

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
            if not next_label.strip():
                # Next row is continuation - use less spacing
                current_y += int(row_height * CONTINUATION_LINE_SPACING)
            else:
                # Next row is normal - use full spacing
                current_y += row_height

    return svg
