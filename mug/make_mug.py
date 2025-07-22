#!/usr/bin/env python3
"""Generate an SVG with x86-64 System V ABI calling convention for a mug."""

import cairosvg


def svg_to_png(svg_path, png_path=None, dpi=300):
    """Convert SVG to PNG using cairosvg."""
    if png_path is None:
        png_path = svg_path.replace(".svg", ".png")

    try:
        # Read the SVG file and convert to PNG with specified DPI
        cairosvg.svg2png(url=svg_path, write_to=png_path, dpi=dpi)

        return png_path
    except Exception as e:
        raise RuntimeError(f"Failed to convert SVG to PNG: {e}") from e


def create_abi_svg(filename="x86_64_abi_mug.svg", width=1100, height=800, generate_png=True):
    # Colors
    bg_color = "transparent"
    text_color = "#000000"
    ce_green = "#67c52a"
    border_color = "#333333"
    header_bg = "#f0f0f0"

    # Font settings
    font_family = "Consolas, Monaco, monospace"
    title_size = 50
    header_size = 28
    text_size = 30

    # Column widths
    col1_width = 200
    col2_width = 375
    col3_width = 375

    # Layout - center the entire design
    table_width = col1_width + col2_width + col3_width
    table_x = (width - table_width) // 2
    table_y = 150
    row_height = 60

    # Table data
    registers = [
        ("RDI", "1st parameter", "this pointer"),
        ("RSI", "2nd parameter", "1st parameter"),
        ("RDX", "3rd parameter", "2nd parameter"),
        ("RCX", "4th parameter", "3rd parameter"),
        ("R8", "5th parameter", "4th parameter"),
        ("R9", "6th parameter", "5th parameter"),
    ]

    # Start SVG
    svg = f"""<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">
  <rect width="{width}" height="{height}" fill="{bg_color}"/>

  <!-- Title -->
  <text x="{table_x}" y="45" font-family="{font_family}" font-size="{title_size}"
        font-weight="bold" fill="{text_color}">x86-64 System V ABI</text>

  <!-- Code examples -->
  <text x="{table_x}" y="90" font-family="{font_family}" font-size="{text_size - 2}"
        fill="{text_color}">free_func(<tspan font-weight="bold" fill="{ce_green}">RDI</tspan>, <tspan font-weight="bold" fill="{ce_green}">RSI</tspan>, <tspan font-weight="bold" fill="{ce_green}">RDX</tspan>, <tspan font-weight="bold" fill="{ce_green}">RCX</tspan>, <tspan font-weight="bold" fill="{ce_green}">R8</tspan>, <tspan font-weight="bold" fill="{ce_green}">R9</tspan>);</text>
  <text x="{table_x}" y="120" font-family="{font_family}" font-size="{text_size - 2}"
        fill="{text_color}"><tspan font-weight="bold" fill="{ce_green}">RDI</tspan>.member_func(<tspan font-weight="bold" fill="{ce_green}">RSI</tspan>, <tspan font-weight="bold" fill="{ce_green}">RDX</tspan>, <tspan font-weight="bold" fill="{ce_green}">RCX</tspan>, <tspan font-weight="bold" fill="{ce_green}">R8</tspan>, <tspan font-weight="bold" fill="{ce_green}">R9</tspan>);</text>

  <!-- Table header background -->
  <rect x="{table_x}" y="{table_y}" width="{table_width}" height="{row_height}"
        fill="{header_bg}" stroke="{border_color}" stroke-width="1"/>

  <!-- Table headers -->
  <text x="{table_x + 25}" y="{table_y + 38}" font-family="{font_family}"
        font-size="{header_size}" font-weight="bold" fill="{text_color}">Register</text>
  <text x="{table_x + col1_width + 25}" y="{table_y + 38}" font-family="{font_family}"
        font-size="{header_size}" font-weight="bold" fill="{text_color}">Free Function</text>
  <text x="{table_x + col1_width + col2_width + 25}" y="{table_y + 38}" font-family="{font_family}"
        font-size="{header_size}" font-weight="bold" fill="{text_color}">Member Function</text>
"""

    # Table rows
    y = table_y + row_height
    for i, (reg, free_func, member_func) in enumerate(registers):
        # Row background (alternate colors)
        row_bg = "#ffffff" if i % 2 == 0 else "#f9f9f9"
        svg += f"""  <rect x="{table_x}" y="{y}" width="{table_width}" height="{row_height}"
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
        y += row_height

    # Additional info
    info_y = y + 40

    info_items = [
        ("Return values:", [("RAX", True), (" (", False), ("RDX", True), (" for 128-bit values)", False)]),
        ("Floating point args:", [("XMM0", True), ("-", False), ("XMM7", True), (" (in order)", False)]),
        ("FP return values:", [("XMM0", True), (" (", False), ("XMM1", True), (" for complex)", False)]),
        ("Stack parameters:", [("16-byte aligned", False)]),
    ]

    for label, parts in info_items:
        svg += f"""  <text x="{table_x}" y="{info_y}" font-family="{font_family}" font-size="{text_size}">
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
        info_y += 28

    # Note about remaining parameters
    svg += f"""
  <!-- Stack note -->
  <text x="{table_x}" y="{info_y + 15}" font-family="{font_family}" font-size="{text_size - 8}"
        fill="{text_color}" opacity="0.6" font-style="italic">
    Parameters beyond 6 integer or 8 FP args are passed on the stack
  </text>
"""

    # Close SVG
    svg += "</svg>\n"

    # Write file
    with open(filename, "w") as f:
        f.write(svg)

    print(f"SVG created: {filename}")
    print(f"Dimensions: {width}x{height}")

    # Generate PNG if requested
    if generate_png:
        try:
            png_filename = svg_to_png(filename)
            print(f"PNG created: {png_filename}")
        except RuntimeError as e:
            print(f"Warning: Could not create PNG: {e}")


if __name__ == "__main__":
    create_abi_svg()
