"""Data model and renderer for architecture cheat-sheet mugs.

The ABI mugs use a fixed shape (register-param table + key/value info table).
An architecture cheat sheet is instead a free-form multi-column grid of titled
blocks (register map, syntax rules, instruction list, flags table), so it has
its own small layout engine here. It reuses the shared text-measurement and
SVG->PNG helpers rather than the ABI-specific table builders.
"""

from dataclasses import dataclass, field
from pathlib import Path

from core.constants import BG_COLOR, BORDER_COLOR, CE_GREEN, DEFAULT_DPI, FOOTER_OPACITY, TEXT_COLOR
from core.svg_generation import svg_to_png
from core.text_measurement import PILTextMeasurer

# Rendering parameters for cheat-sheet mugs. Kept local to this module while the
# design settles; promote to core/constants.py once stable.
TITLE_SIZE = 64
MAX_BODY_SIZE = 50
MIN_BODY_SIZE = 26
HEADING_EXTRA = 2  # heading font size = body size + this
CELL_PAD = 18  # horizontal padding between columns within a block
ROW_LINE_MULT = 1.18  # row pitch as a multiple of body font size
HEADING_LINE_MULT = 1.45  # heading pitch as a multiple of heading font size
BLOCK_GAP = 20  # vertical gap between blocks in a column
COLUMN_GUTTER = 48  # horizontal gap between columns
MARGIN = 44  # outer margin around all content
TITLE_GAP = 28  # gap below the title band
RULE_WIDTH = 3  # stroke width for heading underlines (sublimation-safe)
DIVIDER_COLOR = "#bbbbbb"  # vertical rule between columns
DIVIDER_WIDTH = 3  # stroke width for column dividers (sublimation-safe)
DIAGRAM_BAR_MULT = 1.5  # register-diagram bar height as a multiple of body size
DIAGRAM_BAR_GAP = 8  # vertical gap between diagram bars
DIAGRAM_GUTTER_PAD = 14  # gap between a bar's size label and the bar
DIAGRAM_BORDER_WIDTH = 2  # stroke width for diagram boxes
FOOTER_SIZE = 26  # font size for the optional footer line
# The footer's baseline sits inside the bottom margin, so this only needs to
# keep the last content row from crowding it, not hold the footer itself.
FOOTER_ALLOWANCE = 24


@dataclass
class Cell:
    """A single piece of text in a block row; accent renders it in CE green."""

    text: str
    accent: bool = False


def plain(text: str) -> Cell:
    """A normal (black) cell."""
    return Cell(text)


def green(text: str) -> Cell:
    """An accented (CE green, bold) cell, e.g. a register or mnemonic."""
    return Cell(text, accent=True)


@dataclass
class Block:
    """A titled block: a heading plus a grid of cells aligned into columns.

    Rows may be ragged; column widths are taken from the widest cell present in
    each column position. Notes are full-width lines rendered under the grid
    that do NOT participate in column alignment, so a long aside (e.g. "R10-R15
    same pattern") cannot stretch the table's columns.
    """

    heading: str
    rows: list[list[Cell]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class DiagramBar:
    """One bar in a register-nesting diagram: a sized box split into segments.

    `fraction` is the bar's width relative to the diagram area (e.g. EAX is 0.5
    of RAX); `segments` are equal-width labelled cells within the bar (e.g.
    ["AH", "AL"]). Bars are stacked and right-aligned so they share bit 0.
    """

    bits: str
    fraction: float
    segments: list[str]


@dataclass
class RegDiagram:
    """A register-nesting diagram showing how sub-registers overlap (RAX > EAX
    > AX > AH|AL). Reusable for any width-split ISA (e.g. ARM64 Xn/Wn)."""

    heading: str
    bars: list[DiagramBar]
    notes: list[str] = field(default_factory=list)


# A column holds text blocks and/or register diagrams.
ColumnItem = Block | RegDiagram


@dataclass
class CheatSheet:
    """A whole mug: a title and an explicit assignment of items to columns."""

    title: str
    columns: list[list[ColumnItem]]
    footer: str = ""


def _esc(text: str) -> str:
    """Escape XML special characters for safe embedding in SVG text."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class CheatSheetRenderer:
    """Lays out and renders a CheatSheet to SVG (and optionally PNG)."""

    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self.measurer = PILTextMeasurer()
        self.font_family = self.measurer.get_svg_font_family()

    def _block_natural_width(self, block: Block, body_size: int) -> float:
        """Widest rendered width the block needs at a given body font size."""
        heading_size = body_size + HEADING_EXTRA
        widest = self.measurer.measure_text(block.heading, heading_size, font_weight="bold").width
        # Width of each aligned column position across all rows.
        col_widths: list[float] = []
        for row in block.rows:
            for i, cell in enumerate(row):
                w = self.measurer.measure_text(cell.text, body_size, font_weight="bold").width
                if i >= len(col_widths):
                    col_widths.append(w)
                else:
                    col_widths[i] = max(col_widths[i], w)
        row_total = sum(col_widths) + CELL_PAD * max(0, len(col_widths) - 1)
        widest = max(widest, row_total)
        for note in block.notes:
            widest = max(widest, self.measurer.measure_text(note, body_size).width)
        return widest

    def _diagram_natural_width(self, diagram: RegDiagram, body_size: int) -> float:
        """Min width so the heading, notes, and tightest segment label all fit."""
        heading_size = body_size + HEADING_EXTRA
        widest = self.measurer.measure_text(diagram.heading, heading_size, font_weight="bold").width
        for note in diagram.notes:
            widest = max(widest, self.measurer.measure_text(note, body_size).width)
        # The narrowest segment must be wide enough for its label; scale that
        # requirement up to the full diagram width.
        for bar in diagram.bars:
            seg_fraction = bar.fraction / max(1, len(bar.segments))
            for label in bar.segments:
                label_w = self.measurer.measure_text(label, body_size, font_weight="bold").width
                widest = max(widest, (label_w + CELL_PAD) / seg_fraction)
        return widest

    def _item_natural_width(self, item: ColumnItem, body_size: int) -> float:
        if isinstance(item, RegDiagram):
            return self._diagram_natural_width(item, body_size)
        return self._block_natural_width(item, body_size)

    def _diagram_height(self, diagram: RegDiagram, body_size: int) -> float:
        heading_pitch = (body_size + HEADING_EXTRA) * HEADING_LINE_MULT
        row_pitch = body_size * ROW_LINE_MULT
        bar_pitch = body_size * DIAGRAM_BAR_MULT + DIAGRAM_BAR_GAP
        return heading_pitch + len(diagram.bars) * bar_pitch + len(diagram.notes) * row_pitch

    def _item_height(self, item: ColumnItem, body_size: int) -> float:
        if isinstance(item, RegDiagram):
            return self._diagram_height(item, body_size)
        heading_pitch = (body_size + HEADING_EXTRA) * HEADING_LINE_MULT
        row_pitch = body_size * ROW_LINE_MULT
        return heading_pitch + (len(item.rows) + len(item.notes)) * row_pitch

    def _column_height(self, column: list[ColumnItem], body_size: int) -> float:
        """Total vertical extent of a column's stacked items at a font size."""
        total = sum(self._item_height(item, body_size) + BLOCK_GAP for item in column)
        return total - BLOCK_GAP if column else 0.0

    def _fit_body_size(self, sheet: CheatSheet, column_width: float, available_height: float) -> int:
        """Largest body size at which every item fits its column, in width and height."""
        size = MAX_BODY_SIZE
        while size > MIN_BODY_SIZE:
            widths_ok = all(
                self._item_natural_width(item, size) <= column_width for column in sheet.columns for item in column
            )
            heights_ok = all(self._column_height(column, size) <= available_height for column in sheet.columns)
            if widths_ok and heights_ok:
                break
            size -= 1
        return size

    def _column_layout(self, block: Block, body_size: int) -> list[float]:
        """Per-column-position x offsets (relative to block left) for cells."""
        col_widths: list[float] = []
        for row in block.rows:
            for i, cell in enumerate(row):
                w = self.measurer.measure_text(cell.text, body_size, font_weight="bold").width
                if i >= len(col_widths):
                    col_widths.append(w)
                else:
                    col_widths[i] = max(col_widths[i], w)
        offsets = [0.0]
        for w in col_widths[:-1]:
            offsets.append(offsets[-1] + w + CELL_PAD)
        return offsets

    def _render_heading(self, heading: str, x: float, y: float, body_size: int) -> str:
        """Heading text in CE green with an underline rule beneath it."""
        heading_size = body_size + HEADING_EXTRA
        baseline = y + heading_size
        rule_y = baseline + heading_size * 0.18
        rule_w = self.measurer.measure_text(heading, heading_size, font_weight="bold").width
        return (
            f'  <text x="{x:.0f}" y="{baseline:.0f}" font-family="{self.font_family}" '
            f'font-size="{heading_size}" font-weight="bold" fill="{CE_GREEN}">{_esc(heading)}</text>\n'
            f'  <rect x="{x:.0f}" y="{rule_y:.0f}" width="{rule_w:.0f}" height="{RULE_WIDTH}" fill="{CE_GREEN}"/>\n'
        )

    def _render_note(self, note: str, x: float, y: float, body_size: int) -> str:
        """A dimmed, italic full-width note line with baseline at y + body_size."""
        text_y = y + body_size
        return (
            f'  <text x="{x:.0f}" y="{text_y:.0f}" font-family="{self.font_family}" '
            f'font-size="{body_size}" fill="{TEXT_COLOR}" opacity="0.7" '
            f'font-style="italic">{_esc(note)}</text>\n'
        )

    def _render_diagram(
        self, diagram: RegDiagram, x: float, y: float, body_size: int, column_width: float
    ) -> tuple[str, float]:
        """Render a register-nesting diagram. Returns (svg, y of its bottom)."""
        heading_pitch = (body_size + HEADING_EXTRA) * HEADING_LINE_MULT
        row_pitch = body_size * ROW_LINE_MULT
        bar_height = body_size * DIAGRAM_BAR_MULT
        bar_pitch = bar_height + DIAGRAM_BAR_GAP

        svg = self._render_heading(diagram.heading, x, y, body_size)
        cursor = y + heading_pitch

        # A left gutter holds each bar's bit-size label; bars right-align in the rest.
        gutter = max(self.measurer.measure_text(b.bits, body_size, font_weight="bold").width for b in diagram.bars)
        gutter += DIAGRAM_GUTTER_PAD
        area_x = x + gutter
        area_w = column_width - gutter

        for bar in diagram.bars:
            bar_w = bar.fraction * area_w
            bar_x = area_x + (area_w - bar_w)  # right-aligned
            label_y = cursor + bar_height / 2 + body_size / 3
            # Size label in the gutter.
            svg += (
                f'  <text x="{x:.0f}" y="{label_y:.0f}" font-family="{self.font_family}" '
                f'font-size="{body_size}" fill="{TEXT_COLOR}" opacity="0.7">{_esc(bar.bits)}</text>\n'
            )
            seg_w = bar_w / len(bar.segments)
            for i, seg in enumerate(bar.segments):
                seg_x = bar_x + i * seg_w
                svg += (
                    f'  <rect x="{seg_x:.0f}" y="{cursor:.0f}" width="{seg_w:.0f}" height="{bar_height:.0f}" '
                    f'fill="none" stroke="{BORDER_COLOR}" stroke-width="{DIAGRAM_BORDER_WIDTH}"/>\n'
                )
                svg += (
                    f'  <text x="{seg_x + seg_w / 2:.0f}" y="{label_y:.0f}" font-family="{self.font_family}" '
                    f'font-size="{body_size}" font-weight="bold" fill="{CE_GREEN}" '
                    f'text-anchor="middle">{_esc(seg)}</text>\n'
                )
            cursor += bar_pitch

        for note in diagram.notes:
            svg += self._render_note(note, x, cursor, body_size)
            cursor += row_pitch
        return svg, cursor

    def _render_item(
        self, item: ColumnItem, x: float, y: float, body_size: int, column_width: float
    ) -> tuple[str, float]:
        if isinstance(item, RegDiagram):
            return self._render_diagram(item, x, y, body_size, column_width)
        return self._render_block(item, x, y, body_size)

    def _render_block(self, block: Block, x: float, y: float, body_size: int) -> tuple[str, float]:
        """Render one block at (x, y). Returns (svg, y of the block's bottom)."""
        heading_pitch = (body_size + HEADING_EXTRA) * HEADING_LINE_MULT
        row_pitch = body_size * ROW_LINE_MULT

        svg = self._render_heading(block.heading, x, y, body_size)
        cursor = y + heading_pitch
        offsets = self._column_layout(block, body_size)
        for row in block.rows:
            text_y = cursor + body_size
            for i, cell in enumerate(row):
                cx = x + offsets[i] if i < len(offsets) else x + offsets[-1]
                colour = CE_GREEN if cell.accent else TEXT_COLOR
                weight = "bold" if cell.accent else "normal"
                svg += (
                    f'  <text x="{cx:.0f}" y="{text_y:.0f}" font-family="{self.font_family}" '
                    f'font-size="{body_size}" font-weight="{weight}" fill="{colour}">{_esc(cell.text)}</text>\n'
                )
            cursor += row_pitch
        # Full-width note lines under the grid (not column-aligned), dimmed.
        for note in block.notes:
            svg += self._render_note(note, x, cursor, body_size)
            cursor += row_pitch
        return svg, cursor

    def render(
        self,
        sheet: CheatSheet,
        filename: str,
        *,
        generate_png: bool = True,
        dpi: int = DEFAULT_DPI,
    ) -> None:
        """Render the cheat sheet to an SVG file (and optionally a PNG)."""
        content_x = MARGIN
        content_w = self.width - 2 * MARGIN
        n = len(sheet.columns)
        column_width = (content_w - COLUMN_GUTTER * (n - 1)) / n if n else content_w

        title_y = MARGIN + TITLE_SIZE
        content_top = title_y + TITLE_GAP
        footer_reserve = FOOTER_ALLOWANCE if sheet.footer else 0
        available_height = self.height - content_top - MARGIN - footer_reserve
        body_size = self._fit_body_size(sheet, column_width, available_height)

        svg = (
            f'<svg width="{self.width}" height="{self.height}" xmlns="http://www.w3.org/2000/svg">\n'
            f'  <rect width="{self.width}" height="{self.height}" fill="{BG_COLOR}"/>\n'
        )

        # Title band, centred.
        svg += (
            f'  <text x="{self.width // 2}" y="{title_y:.0f}" font-family="{self.font_family}" '
            f'font-size="{TITLE_SIZE}" font-weight="bold" fill="{CE_GREEN}" '
            f'text-anchor="middle">{_esc(sheet.title)}</text>\n'
        )

        max_bottom: float = content_top
        for c, column in enumerate(sheet.columns):
            x = content_x + c * (column_width + COLUMN_GUTTER)
            y: float = content_top
            for item in column:
                item_svg, y = self._render_item(item, x, y, body_size, column_width)
                y += BLOCK_GAP
                svg += item_svg
            max_bottom = max(max_bottom, y)

        # Vertical dividers between columns, spanning the rendered content.
        divider_bottom = max_bottom - BLOCK_GAP
        for c in range(n - 1):
            x_div = content_x + c * (column_width + COLUMN_GUTTER) + column_width + COLUMN_GUTTER / 2
            svg += (
                f'  <rect x="{x_div:.0f}" y="{content_top:.0f}" width="{DIVIDER_WIDTH}" '
                f'height="{divider_bottom - content_top:.0f}" fill="{DIVIDER_COLOR}"/>\n'
            )

        if sheet.footer:
            footer_y = self.height - MARGIN + FOOTER_SIZE
            svg += (
                f'  <text x="{self.width // 2}" y="{footer_y:.0f}" font-family="{self.font_family}" '
                f'font-size="{FOOTER_SIZE}" fill="{TEXT_COLOR}" opacity="{FOOTER_OPACITY}" '
                f'font-style="italic" text-anchor="middle">{_esc(sheet.footer)}</text>\n'
            )

        svg += "</svg>\n"
        Path(filename).write_text(svg, encoding="utf-8")

        print(f"SVG created: {filename}  ({self.width}x{self.height}, body {body_size}pt)")
        if max_bottom > self.height - MARGIN:
            overflow = max_bottom - (self.height - MARGIN)
            print(f"WARNING: content overflows bottom margin by {overflow:.0f}px - trim content or raise height")
        for column in sheet.columns:
            for item in column:
                over = self._item_natural_width(item, body_size) - column_width
                if over > 0:
                    print(f"WARNING: '{item.heading}' is {over:.0f}px too wide for its column - shorten its text")

        if generate_png:
            try:
                png = svg_to_png(filename, dpi=dpi)
                print(f"PNG created: {png}")
            except RuntimeError as e:
                print(f"Warning: could not create PNG: {e}")
