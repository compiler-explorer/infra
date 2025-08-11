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
    # Create layout using new system with styling
    layout = MugLayout(
        title="x86-64 Windows (MSVC) ABI",
        code_examples=[],  # No longer used
        table_headers=["RCX", "RDX", "R8", "R9"],
        table_rows=[TableRow(cells=["1st", "2nd", "3rd", "4th"]), TableRow(cells=["this", "1st", "2nd", "3rd"])],
        info_items=[
            ("Return values", "RAX (+ RDX for 128-bit)"),
            ("FP args", "XMM0-XMM3"),
            ("", "(XMM# matches arg pos)"),
            ("FP return", "XMM0"),
            ("Caller-saved", "RAX RCX RDX R8-R11"),
            ("", "XMM0-XMM5"),
            ("Callee-saved", "RBX RBP RDI RSI R12-R15"),
            ("", "XMM6-XMM15"),
        ],
        footer_lines=["Args beyond 4 on stack; 32-byte shadow space needed"],
        title_size=72,
        header_size=36,
        text_size=38,
        info_text_size=42,
        table_row_padding=12,  # Padding above/below text in table rows
        footer_spacing=40,
    )

    # Use layout engine
    engine = LayoutEngine(width, height)
    positions = engine.layout_mug(layout)

    # Get proper SVG font family name
    svg_font_family = engine.svg_font_family

    # Generate SVG
    svg = f"""<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">
  <rect width="{width}" height="{height}" fill="{BG_COLOR}"/>

  <!-- Title (horizontal at top) -->
  <text x="{positions["title"]["x"]}" y="{positions["title"]["y"]}" font-family="{svg_font_family}" font-size="{positions["title"]["size"]}"
        font-weight="bold" fill="{CE_GREEN}" text-anchor="middle">{layout.title}</text>
"""

    # Main table with registers as headers
    table_svg = create_horizontal_table(
        headers=layout.table_headers,
        rows=[row.cells for row in layout.table_rows],
        row_labels=[ROW_LABEL_FUNCTION, ROW_LABEL_MEMBER],
        table_x=positions["table"]["x"],
        table_y=positions["table"]["y"],
        col_width=positions["table"]["col_width"],
        row_height=positions["table"]["row_height"],
        label_width=positions["table"]["label_width"],
        font_family=svg_font_family,
        header_size=positions["table"]["header_size"],
        text_size=positions["table"]["text_size"],
        text_color=TEXT_COLOR,
        ce_green=CE_GREEN,
        border_color=BORDER_COLOR,
        header_bg=HEADER_BG,
    )
    svg += table_svg

    # Info table
    info_table_svg = create_info_table(
        rows=layout.info_items,
        table_x=positions["info_items"]["x"],
        table_y=positions["info_items"]["y"],
        table_width=positions["info_items"]["width"],
        row_height=positions["info_items"]["row_height"],
        font_family=svg_font_family,
        text_size=positions["info_items"]["text_size"],
        text_color=TEXT_COLOR,
        ce_green=CE_GREEN,
        border_color=BORDER_COLOR,
        header_bg=HEADER_BG,
        measurer=engine.measurer,
    )
    svg += info_table_svg

    # Footer lines (already optimized by layout engine)
    for i, line in enumerate(positions["footer"]["lines"]):
        line_y = positions["footer"]["y"] + (i * positions["footer"]["line_height"])
        svg += f"""  <text x="{positions["footer"]["x"]}" y="{line_y}" font-family="{svg_font_family}" font-size="{positions["footer"]["size"]}"
        fill="{TEXT_COLOR}" opacity="{FOOTER_OPACITY}" font-style="italic" text-anchor="middle">{line}</text>
"""

    # Close SVG
    svg += "</svg>\n"

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
    """Generate x86-64 Windows (MSVC) ABI reference design for mugs.

    FILENAME is the output SVG file path (required).

    \b
    Examples:
      # Generate default SVG and PNG
      uv run mugs/make_x86_64_msvc_mug.py output.svg

      # Custom dimensions
      uv run mugs/make_x86_64_msvc_mug.py output.svg --width 1200 --height 900

      # SVG only (no PNG)
      uv run mugs/make_x86_64_msvc_mug.py output.svg --no-png

      # High-resolution PNG
      uv run mugs/make_x86_64_msvc_mug.py output.svg --dpi 600
    """
    create_abi_svg(filename=filename, width=width, height=height, generate_png=not no_png, dpi=dpi)


if __name__ == "__main__":
    main()
