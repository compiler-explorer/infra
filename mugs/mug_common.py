import cairosvg

# Common color constants
BG_COLOR = "transparent"
TEXT_COLOR = "#000000"
CE_GREEN = "#67c52a"
BORDER_COLOR = "#333333"
HEADER_BG = "#f0f0f0"

# Common font and layout constants
FONT_FAMILY = "Consolas, Monaco, monospace"

# Column widths
COL1_WIDTH = 200
COL2_WIDTH = 375
COL3_WIDTH = 375

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

    # Register name (with CE green accent)
    svg += f"""  <text x="{table_x + 25}" y="{y + 38}" font-family="{font_family}"
        font-size="{text_size}" font-weight="bold" fill="{ce_green}">{reg}</text>
"""

    # Free function parameter
    svg += f"""  <text x="{table_x + col1_width + 25}" y="{y + 38}" font-family="{font_family}"
        font-size="{text_size}" fill="{text_color}">{free_func}</text>
"""

    # Member function parameter
    if member_func == "this pointer":
        svg += f"""  <text x="{table_x + col1_width + col2_width + 25}" y="{y + 38}" font-family="{font_family}"
        font-size="{text_size}" font-weight="bold" fill="{ce_green}">{member_func}</text>
"""
    else:
        svg += f"""  <text x="{table_x + col1_width + col2_width + 25}" y="{y + 38}" font-family="{font_family}"
        font-size="{text_size}" fill="{text_color}">{member_func}</text>
"""

    return svg
