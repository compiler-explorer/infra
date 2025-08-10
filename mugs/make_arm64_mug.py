import click
from mug_common import (
    BG_COLOR,
    BORDER_COLOR,
    CE_GREEN,
    FONT_FAMILY,
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
    filename: str, width: int = 1100, height: int = 800, generate_png: bool = True, dpi: int = 300
) -> None:
    # Create layout using new system with styling
    layout = MugLayout(
        title="ARM64 (AAPCS) ABI",
        code_examples=[],  # No longer used
        table_headers=["X0", "X1", "X2", "X3", "X4", "X5", "X6", "X7"],  # 8 registers
        table_rows=[
            TableRow(cells=["1st", "2nd", "3rd", "4th", "5th", "6th", "7th", "8th"]),
            TableRow(cells=["this", "1st", "2nd", "3rd", "4th", "5th", "6th", "7th"]),
        ],
        info_items=[
            ("Return values", "X0 (X1 for 128-bit)"),
            ("Special regs", "X8 indirect, X29 FP"),
            ("", "X30 LR, SP stack"),
            ("FP args", "V0-V7"),
            ("FP return", "V0/V1"),
            ("Caller-saved", "X0-X17 V0-V7 V16-V31"),
            ("Callee-saved", "X19-X28 V8-V15"),
            ("", "(lower 64 bits)"),
        ],
        footer_lines=["Parameters beyond 8 int/FP args on stack (16-byte aligned)"],
        title_size=72,
        header_size=36,
        text_size=38,
        info_text_size=42,
        row_height=70,
        footer_spacing=40,
    )

    # Use layout engine
    engine = LayoutEngine(width, height)
    positions = engine.layout_mug(layout)

    # Generate SVG
    svg = f"""<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">
  <rect width="{width}" height="{height}" fill="{BG_COLOR}"/>

  <!-- Title (horizontal at top) -->
  <text x="{positions["title"]["x"]}" y="{positions["title"]["y"]}" font-family="{FONT_FAMILY}" font-size="{positions["title"]["size"]}"
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
        font_family=FONT_FAMILY,
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
        font_family=FONT_FAMILY,
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
        svg += f"""  <text x="{positions["footer"]["x"]}" y="{line_y}" font-family="{FONT_FAMILY}" font-size="{positions["footer"]["size"]}"
        fill="{TEXT_COLOR}" opacity="0.6" font-style="italic" text-anchor="middle">{line}</text>
"""

    # Close SVG
    svg += "</svg>\n"

    # Write file
    with open(filename, "w") as f:
        f.write(svg)

    print(f"SVG created: {filename}")
    print(f"Dimensions: {width}x{height}")

    # Cleanup
    engine.cleanup()

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
