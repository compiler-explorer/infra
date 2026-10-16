"""Abstract base class for architecture cheat-sheet mug generators."""

from abc import ABC, abstractmethod

import click
from core.cheatsheet import CheatSheet, CheatSheetRenderer

# Cheat sheets keep the existing ABI-mug aspect ratio (~1.4:1) so they print on
# the same mugs; landscape suits the multi-column grid.
DEFAULT_WIDTH = 1400
DEFAULT_HEIGHT = 1000
DEFAULT_DPI = 300


class CheatSheetGenerator(ABC):
    """Abstract base class for architecture cheat-sheet generators."""

    @abstractmethod
    def get_cheatsheet(self) -> CheatSheet:
        """Return the CheatSheet data structure for this architecture."""

    def get_click_command(self):
        """Return a Click command for this generator."""

        @click.command()
        @click.argument("filename", type=click.Path())
        @click.option("--width", default=DEFAULT_WIDTH, help=f"SVG width in pixels (default: {DEFAULT_WIDTH})")
        @click.option("--height", default=DEFAULT_HEIGHT, help=f"SVG height in pixels (default: {DEFAULT_HEIGHT})")
        @click.option("--no-png", is_flag=True, help="Skip PNG generation")
        @click.option("--dpi", default=DEFAULT_DPI, help=f"DPI for PNG generation (default: {DEFAULT_DPI})")
        def main(filename: str, width: int, height: int, no_png: bool, dpi: int) -> None:
            """Generate an architecture cheat-sheet design for mugs.

            FILENAME is the output SVG file path (required).
            """
            renderer = CheatSheetRenderer(width, height)
            renderer.render(self.get_cheatsheet(), filename, generate_png=not no_png, dpi=dpi)

        return main
