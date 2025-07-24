import click
from mug_common import (
    BG_COLOR,
    BORDER_COLOR,
    CE_GREEN,
    COL1_WIDTH,
    COL2_WIDTH,
    COL3_WIDTH,
    FONT_FAMILY,
    HEADER_BG,
    TABLE_Y,
    TEXT_COLOR,
    create_table_row,
    render_info_items,
    svg_to_png,
)


def create_abi_svg(
    filename: str, width: int = 1100, height: int = 800, generate_png: bool = True, dpi: int = 300
) -> None:
    # Font settings (ABI-specific sizes)
    title_size = 50
    header_size = 28
    text_size = 30

    # Layout - center the entire design
    table_width = COL1_WIDTH + COL2_WIDTH + COL3_WIDTH
    table_x = (width - table_width) // 2
    row_height = 48

    # Table data
    registers = [
        ("X0", "1st parameter", "this pointer"),
        ("X1", "2nd parameter", "1st parameter"),
        ("X2", "3rd parameter", "2nd parameter"),
        ("X3", "4th parameter", "3rd parameter"),
        ("X4", "5th parameter", "4th parameter"),
        ("X5", "6th parameter", "5th parameter"),
        ("X6", "7th parameter", "6th parameter"),
        ("X7", "8th parameter", "7th parameter"),
    ]

    # Start SVG
    svg = f"""<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">
  <rect width="{width}" height="{height}" fill="{BG_COLOR}"/>

  <!-- Title -->
  <text x="{table_x}" y="45" font-family="{FONT_FAMILY}" font-size="{title_size}"
        font-weight="bold" fill="{TEXT_COLOR}">ARM64 (AAPCS) ABI</text>

  <!-- Code examples -->
  <text x="{table_x}" y="90" font-family="{FONT_FAMILY}" font-size="{text_size - 2}"
        fill="{TEXT_COLOR}">free_func(<tspan font-weight="bold" fill="{CE_GREEN}">X0</tspan>, <tspan font-weight="bold" fill="{CE_GREEN}">X1</tspan>, <tspan font-weight="bold" fill="{CE_GREEN}">X2</tspan>, <tspan font-weight="bold" fill="{CE_GREEN}">X3</tspan>, <tspan font-weight="bold" fill="{CE_GREEN}">X4</tspan>, <tspan font-weight="bold" fill="{CE_GREEN}">X5</tspan>, <tspan font-weight="bold" fill="{CE_GREEN}">X6</tspan>, <tspan font-weight="bold" fill="{CE_GREEN}">X7</tspan>);</text>
  <text x="{table_x}" y="120" font-family="{FONT_FAMILY}" font-size="{text_size - 2}"
        fill="{TEXT_COLOR}"><tspan font-weight="bold" fill="{CE_GREEN}">X0</tspan>.member_func(<tspan font-weight="bold" fill="{CE_GREEN}">X1</tspan>, <tspan font-weight="bold" fill="{CE_GREEN}">X2</tspan>, <tspan font-weight="bold" fill="{CE_GREEN}">X3</tspan>, <tspan font-weight="bold" fill="{CE_GREEN}">X4</tspan>, <tspan font-weight="bold" fill="{CE_GREEN}">X5</tspan>, <tspan font-weight="bold" fill="{CE_GREEN}">X6</tspan>, <tspan font-weight="bold" fill="{CE_GREEN}">X7</tspan>);</text>

  <!-- Table header background -->
  <rect x="{table_x}" y="{TABLE_Y}" width="{table_width}" height="{row_height}"
        fill="{HEADER_BG}" stroke="{BORDER_COLOR}" stroke-width="1"/>

  <!-- Table headers -->
  <text x="{table_x + 25}" y="{TABLE_Y + 38}" font-family="{FONT_FAMILY}"
        font-size="{header_size}" font-weight="bold" fill="{TEXT_COLOR}">Register</text>
  <text x="{table_x + COL1_WIDTH + 25}" y="{TABLE_Y + 38}" font-family="{FONT_FAMILY}"
        font-size="{header_size}" font-weight="bold" fill="{TEXT_COLOR}">Free Function</text>
  <text x="{table_x + COL1_WIDTH + COL2_WIDTH + 25}" y="{TABLE_Y + 38}" font-family="{FONT_FAMILY}"
        font-size="{header_size}" font-weight="bold" fill="{TEXT_COLOR}">Member Function</text>
"""

    # Table rows
    y = TABLE_Y + row_height
    for i, (reg, free_func, member_func) in enumerate(registers):
        svg += create_table_row(
            i,
            reg,
            free_func,
            member_func,
            table_x,
            y,
            table_width,
            row_height,
            COL1_WIDTH,
            COL2_WIDTH,
            FONT_FAMILY,
            text_size,
            TEXT_COLOR,
            CE_GREEN,
            BORDER_COLOR,
        )
        y += row_height

    # Additional info
    info_y = y + 40

    info_items = [
        (
            "Return values:",
            [
                ("X0", True),
                (" (", False),
                ("X1", True),
                (" for 128-bit)", False),
            ],
        ),
        (
            "Special regs:",
            [
                ("X8", True),
                (" indirect, ", False),
                ("X29", True),
                (" FP, ", False),
                ("X30", True),
                (" LR, ", False),
                ("SP", True),
                (" stack", False),
            ],
        ),
        (
            "FP args/return:",
            [
                ("V0", True),
                ("-", False),
                ("V7", True),
                (" args, ", False),
                ("V0", True),
                ("/", False),
                ("V1", True),
                (" return", False),
            ],
        ),
        (
            "Caller-saved:",
            [
                ("X0", True),
                ("-", False),
                ("X17", True),
                (" ", False),
                ("V0", True),
                ("-", False),
                ("V7", True),
                (" ", False),
                ("V16", True),
                ("-", False),
                ("V31", True),
            ],
        ),
        (
            "Callee-saved:",
            [
                ("X19", True),
                ("-", False),
                ("X28", True),
                (" ", False),
                ("V8", True),
                ("-", False),
                ("V15", True),
                (" (lower 64 bits)", False),
            ],
        ),
    ]

    info_svg, info_y = render_info_items(info_items, table_x, info_y, FONT_FAMILY, text_size, TEXT_COLOR, CE_GREEN)
    svg += info_svg

    # Note about remaining parameters
    svg += f"""
  <!-- Stack note -->
  <text x="{table_x}" y="{info_y + 15}" font-family="{FONT_FAMILY}" font-size="{text_size - 8}"
        fill="{TEXT_COLOR}" opacity="0.6" font-style="italic">
    Parameters beyond 8 int/FP args on stack (16-byte aligned)
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
            png_filename = svg_to_png(filename, dpi=dpi)
            print(f"PNG created: {png_filename}")
        except RuntimeError as e:
            print(f"Warning: Could not create PNG: {e}")


@click.command()
@click.argument("filename", type=click.Path())
@click.option("--width", default=1100, help="SVG width in pixels (default: 1100)")
@click.option("--height", default=800, help="SVG height in pixels (default: 800)")
@click.option("--no-png", is_flag=True, help="Skip PNG generation")
@click.option("--dpi", default=300, help="DPI for PNG generation (default: 300)")
def main(filename, width, height, no_png, dpi):
    """Generate ARM64 (AAPCS) ABI reference design for mugs.

    FILENAME is the output SVG file path (required).

    \b
    Examples:
      # Generate default SVG and PNG
      uv run mugs/make_arm64_mug.py output.svg

      # Custom dimensions
      uv run mugs/make_arm64_mug.py output.svg --width 1200 --height 900

      # SVG only (no PNG)
      uv run mugs/make_arm64_mug.py output.svg --no-png

      # High-resolution PNG
      uv run mugs/make_arm64_mug.py output.svg --dpi 600
    """
    create_abi_svg(filename=filename, width=width, height=height, generate_png=not no_png, dpi=dpi)


if __name__ == "__main__":
    main()
