"""Abstract base class for ABI mug generators."""

from abc import ABC, abstractmethod
from pathlib import Path

import click
from core.constants import (
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
)
from core.data_structures import MugLayout
from core.layout_engine import LayoutEngine
from core.svg_generation import create_horizontal_table, create_info_table, svg_to_png


class ABIMugGenerator(ABC):
    """Abstract base class for ABI mug generators."""

    @abstractmethod
    def get_layout_data(self) -> MugLayout:
        """Return the MugLayout data structure for this ABI."""
        pass

    @abstractmethod
    def get_title(self) -> str:
        """Return the title for this ABI."""
        pass

    def create_abi_svg(
        self,
        filename: str,
        width: int = DEFAULT_WIDTH,
        height: int = DEFAULT_HEIGHT,
        generate_png: bool = True,
        dpi: int = DEFAULT_DPI,
    ) -> None:
        """Create the ABI SVG and optionally PNG file."""
        # Get layout data from subclass
        layout = self.get_layout_data()

        # Use layout engine to calculate positions
        engine = LayoutEngine(width, height)
        positions = engine.layout_mug(layout)

        # Get proper SVG font family name
        svg_font_family = engine.svg_font_family

        # Start SVG
        svg = f'''<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">
  <rect width="{width}" height="{height}" fill="{BG_COLOR}"/>

  <!-- Title (horizontal at top) -->
  <text x="{positions["title"]["x"]}" y="{positions["title"]["y"]}" font-family="{svg_font_family}" font-size="{positions["title"]["size"]}"
        font-weight="bold" fill="{CE_GREEN}" text-anchor="middle">{layout.title}</text>
'''

        # Horizontal table with registers as headers
        table_pos = positions["table"]

        # Convert table data to format expected by create_horizontal_table
        table_data = []
        for row in layout.table_rows:
            table_data.append(row.cells)

        svg += create_horizontal_table(
            layout.table_headers,  # Register names
            table_data,  # Cell data
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
        # Footer lines
        for i, line in enumerate(positions["footer"]["lines"]):
            line_y = positions["footer"]["y"] + (i * positions["footer"]["line_height"])
            svg += f'\n  <text x="{positions["footer"]["x"]}" y="{line_y}" font-family="{svg_font_family}" font-size="{positions["footer"]["size"]}"\n        fill="{TEXT_COLOR}" opacity="{FOOTER_OPACITY}" font-style="italic" text-anchor="middle">{line}</text>'

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

    def get_click_command(self):
        """Return a Click command for this generator."""

        @click.command()
        @click.argument("filename", type=click.Path())
        @click.option("--width", default=DEFAULT_WIDTH, help=f"SVG width in pixels (default: {DEFAULT_WIDTH})")
        @click.option("--height", default=DEFAULT_HEIGHT, help=f"SVG height in pixels (default: {DEFAULT_HEIGHT})")
        @click.option("--no-png", is_flag=True, help="Skip PNG generation")
        @click.option("--dpi", default=DEFAULT_DPI, help=f"DPI for PNG generation (default: {DEFAULT_DPI})")
        def main(filename: str, width: int, height: int, no_png: bool, dpi: int) -> None:
            """Generate ABI reference design for mugs.

            FILENAME is the output SVG file path (required).

            \\b
            Examples:
              # Generate default SVG and PNG
              uv run mugs/make_[name]_mug.py output.svg

              # Custom dimensions
              uv run mugs/make_[name]_mug.py output.svg --width 1200 --height 900

              # SVG only (no PNG)
              uv run mugs/make_[name]_mug.py output.svg --no-png

              # High-resolution PNG
              uv run mugs/make_[name]_mug.py output.svg --dpi 600
            """
            self.create_abi_svg(filename=filename, width=width, height=height, generate_png=not no_png, dpi=dpi)

        return main
