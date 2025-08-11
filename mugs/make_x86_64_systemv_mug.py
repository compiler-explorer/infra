from pathlib import Path

import click
from mug_common import (
    BG_COLOR,
    BORDER_COLOR,
    CE_GREEN,
    DEFAULT_DPI,
    DEFAULT_HEIGHT,
    DEFAULT_WIDTH,
    FOOTER_OPACITY,
    HEADER_BG,
    ROW_LABEL_FUNCTION,
    ROW_LABEL_MEMBER,
    TEXT_COLOR,
    LayoutEngine,
    MugLayout,
    TableRow,
    create_horizontal_table,
    create_info_table,
    svg_to_png,
)


def create_abi_svg(
    filename: str,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    generate_png: bool = True,
    dpi: int = DEFAULT_DPI,
) -> None:
    # Create layout data structure - new horizontal format with styling
    layout = MugLayout(
        title="x86-64 System V ABI",
        code_examples=[],  # No longer used
        table_headers=["RDI", "RSI", "RDX", "RCX", "R8", "R9"],  # Register names
        table_rows=[
            TableRow(["1st", "2nd", "3rd", "4th", "5th", "6th"]),  # Function parameters
            TableRow(["this", "1st", "2nd", "3rd", "4th", "5th"]),  # Member parameters
        ],
        info_items=[
            ("Return values", "RAX (RDX for 128-bit)"),
            ("FP args", "XMM0-XMM7"),
            ("FP return", "XMM0/XMM1"),
            ("Caller-saved", "RAX RCX RDX RSI RDI"),
            ("", "R8-R11 XMM0-XMM15"),
            ("Callee-saved", "RBX RBP R12-R15"),
        ],
        footer_lines=["Parameters beyond 6 integer or 8 FP args are passed on the stack"],
        title_size=72,
        header_size=36,
        text_size=38,
        info_text_size=42,
        row_height=70,
        footer_spacing=90,
    )

    # Use layout engine to calculate positions
    engine = LayoutEngine(width, height)
    positions = engine.layout_mug(layout)

    # Get proper SVG font family name
    svg_font_family = engine.svg_font_family

    # Start SVG
    svg = f"""<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">
  <rect width="{width}" height="{height}" fill="{BG_COLOR}"/>

  <!-- Title (horizontal at top) -->
  <text x="{positions["title"]["x"]}" y="{positions["title"]["y"]}" font-family="{svg_font_family}" font-size="{positions["title"]["size"]}"
        font-weight="bold" fill="{CE_GREEN}" text-anchor="middle">{layout.title}</text>
"""

    # Horizontal table with registers as headers
    table_pos = positions["table"]

    # Convert table data to format expected by create_horizontal_table
    table_data = []
    for row in layout.table_rows:
        table_data.append(row.cells)

    svg += create_horizontal_table(
        layout.table_headers,  # Register names: RDI, RSI, etc.
        table_data,  # [["1st", "2nd", ...], ["this", "1st", ...]]
        [ROW_LABEL_FUNCTION, ROW_LABEL_MEMBER],  # Row labels using constants
        table_pos["x"],
        table_pos["y"],
        table_pos["col_width"],
        table_pos["row_height"],
        table_pos["label_width"],
        svg_font_family,
        table_pos["header_size"],
        table_pos["text_size"],
        TEXT_COLOR,
        CE_GREEN,
        BORDER_COLOR,
        HEADER_BG,
    )

    # Info table using new format
    info_table_pos = positions["info_items"]
    info_table_svg = create_info_table(
        layout.info_items,
        info_table_pos["x"],
        info_table_pos["y"],
        info_table_pos["width"],
        info_table_pos["row_height"],
        svg_font_family,
        info_table_pos["text_size"],
        TEXT_COLOR,
        CE_GREEN,
        BORDER_COLOR,
        HEADER_BG,
        engine.measurer,
    )
    svg += info_table_svg

    # Footer lines (already optimized by layout engine)
    svg += """
  <!-- Footer lines -->"""

    for i, line in enumerate(positions["footer"]["lines"]):
        line_y = positions["footer"]["y"] + (i * positions["footer"]["line_height"])
        svg += f"""
  <text x="{positions["footer"]["x"]}" y="{line_y}" font-family="{svg_font_family}" font-size="{positions["footer"]["size"]}"
        fill="{TEXT_COLOR}" opacity="{FOOTER_OPACITY}" font-style="italic" text-anchor="middle">{line}</text>"""

    # Close SVG
    svg += "\n</svg>\n"

    # Write file
    Path(filename).write_text(svg, encoding="utf-8")

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
@click.option("--width", default=DEFAULT_WIDTH, help=f"SVG width in pixels (default: {DEFAULT_WIDTH})")
@click.option("--height", default=DEFAULT_HEIGHT, help=f"SVG height in pixels (default: {DEFAULT_HEIGHT})")
@click.option("--no-png", is_flag=True, help="Skip PNG generation")
@click.option("--dpi", default=DEFAULT_DPI, help=f"DPI for PNG generation (default: {DEFAULT_DPI})")
def main(filename, width, height, no_png, dpi):
    """Generate x86-64 System V ABI reference design for mugs.

    FILENAME is the output SVG file path (required).

    \b
    Examples:
      # Generate default SVG and PNG
      uv run mugs/make_x86_64_systemv_mug.py output.svg

      # Custom dimensions
      uv run mugs/make_x86_64_systemv_mug.py output.svg --width 1200 --height 900

      # SVG only (no PNG)
      uv run mugs/make_x86_64_systemv_mug.py output.svg --no-png

      # High-resolution PNG
      uv run mugs/make_x86_64_systemv_mug.py output.svg --dpi 600
    """
    create_abi_svg(filename=filename, width=width, height=height, generate_png=not no_png, dpi=dpi)


if __name__ == "__main__":
    main()
