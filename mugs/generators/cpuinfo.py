"""/proc/cpuinfo decoder mug: an annotated cpuinfo excerpt over a codename/core lookup.

The lookup is drawn as a two-set Venn diagram cut into rows. Each row is a core
microarchitecture; the green tint is the set of chips built on the row's P-core,
the outline the set built on its E-core, and the column where they overlap holds
the hybrid chips that use both. AMD's dense "c" cores play the E-core role.

The layout is bespoke (an annotated code excerpt plus a spanning-region table),
so this module draws it directly rather than through CheatSheetRenderer, reusing
the same title/margin/footer constants so it sits in the same series.
"""

from dataclasses import dataclass
from pathlib import Path

import click
from core.cheatsheet import FOOTER_SIZE, MARGIN, TITLE_GAP, TITLE_SIZE
from core.constants import BG_COLOR, CE_GREEN, DEFAULT_DPI, FOOTER_OPACITY, TEXT_COLOR
from core.svg_generation import svg_to_png
from core.text_measurement import PILTextMeasurer

WIDTH = 1400
HEIGHT = 1000

CPUINFO_SIZE = 28
CPUINFO_PITCH = 37
ANNOTATION_SIZE = 25
ANNOTATION_X = 498  # annotations on the same line start here, clear of the longest short value
HIGHLIGHT_RULE = 3  # underline under the digits that matter
HIGHLIGHT_DROP = 6  # underline offset below the baseline

BAND_SIZE = 24
BAND_HEADER_SIZE = 23
BAND_PITCH = 32
BAND_GAP = 14  # space between the cpuinfo excerpt and the band
CELL_PAD = 8
# gen | P-core | P only | hybrid | E only | E-core; P only takes whatever is left.
BAND_COLUMNS = [150, 222, 0, 200, 275, 150]
P_TINT = "#d9f0c9"  # about 25% CE green: light tints vanish in dye-sublimation
REGION_RULE = 3

KEY_SIZE = 21
KEY_PITCH = 28
KEY_GAP = 10

LEVEL_SIZE = 25
LEVEL_GAP = 16
LEVEL_BOX_HEIGHT = 52
LEVEL_BOX_GAP = 20
LEVEL_RULE = 2


@dataclass
class Span:
    """A run of text in a cpuinfo line; highlighted runs are green, bold and underlined."""

    text: str
    highlight: bool = False


@dataclass
class CpuinfoLine:
    """One excerpt line. An annotation with `under_highlight` sits on its own line
    beneath the previous line's first highlighted span, with an up arrow."""

    spans: list[Span]
    annotation: str = ""
    under_highlight: bool = False


@dataclass
class CoreRow:
    gen: str
    p_core: str
    p_only: str = ""
    hybrid: str = ""
    e_only: str = ""
    e_core: str = ""


# An Ice Lake-SP cloud box (AWS c6i): every highlighted digit is explained.
CPUINFO = [
    CpuinfoLine([Span("cpu family : "), Span("6", True)], "← since 1995; Nova Lake will be 18"),
    CpuinfoLine([Span("model      : "), Span("106", True)], "← decimal! 0x6A = Ice Lake-SP"),
    CpuinfoLine([Span("model name : Intel(R) Xeon(R) Platinum "), Span("83", True), Span("75C CPU")]),
    CpuinfoLine([], "↑ 8=Platinum 3=gen 3: Ice Lake (or Cooper)", under_highlight=True),
    CpuinfoLine(
        [Span("flags      : … avx2 … "), Span("avx512f", True), Span(" …")],
        "   ← + bw cd dq vl = x86-64-v4",
    ),
]

# Core names and the product-to-core mapping follow the comments in the Linux
# kernel's arch/x86/include/asm/intel-family.h.
INTEL = [
    CoreRow("6-10 X1-2", "Skylake", "Kaby Coffee Comet Cascade"),
    CoreRow("10G X3", "Sunny Cove", "Ice Lake (+SP)", "Lakefield", "", "Tremont"),
    CoreRow("11", "Willow/Cypress", "Tiger · Rocket Lake"),
    CoreRow("12 X4", "Golden Cove", "Sapphire Rapids", "Alder Lake", "Alder Lake-N", "Gracemont"),
    CoreRow("13 14 X5", "Raptor Cove", "Emerald Rapids", "Raptor Lake", "", "Gracemont"),
    CoreRow("U1 2xxU", "Redwood Cove", "Granite Rapids", "Meteor Lake", "Sierra Forest", "Crestmont"),
    CoreRow("U2 S/H/V", "Lion Cove", "", "Arrow/Lunar", "", "Skymont"),
    CoreRow("U3", "Cougar Cove", "", "Panther Lake", "Clearwater Forest", "Darkmont"),
]

AMD = [
    CoreRow("EPYC 1-3", "Zen 1-3", "Naples Rome Milan"),
    CoreRow("7xxx 9xx4", "Zen 4", "Genoa Raphael", "Phoenix 2", "Bergamo", "Zen 4c"),
    CoreRow("9xxx 9xx5", "Zen 5", "Turin Granite Ridge", "Strix Point", "Turin Dense", "Zen 5c"),
]

KEY = [
    "N = Core iN · UN = Core Ultra N · XN = Xeon Scalable gen (2nd digit) · Xeon 6 = 6xxxP / 6xxxE",
    "AMD: Ryzen Nxxx · EPYC xxxN · laptop Ryzen 7x40: 3rd digit = Zen gen",
]

LEVELS = [("v2", "sse4_2 popcnt …"), ("v3", "avx2 bmi2 fma …"), ("v4", "avx512 f bw cd dq vl")]


def _esc(text: str) -> str:
    """Escape XML special characters for safe embedding in SVG text."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class CpuinfoMugRenderer:
    """Draws the cpuinfo decoder mug to SVG, warning about anything that doesn't fit."""

    def __init__(self) -> None:
        self.measurer = PILTextMeasurer()
        self.font_family = self.measurer.get_svg_font_family()
        self.warnings: list[str] = []
        self.svg: list[str] = []

    def _width(self, text: str, size: int, bold: bool = False) -> float:
        weight = "bold" if bold else "normal"
        return self.measurer.measure_text(text, size, font_weight=weight).width

    def _advance(self, text: str, size: int) -> float:
        """Pen advance for monospaced text. measure_text uses a bounding box, which
        drops trailing spaces, so spans like "Platinum " would land short."""
        sample = "0" * 100
        per_char = self._width(sample, size) / len(sample)
        return per_char * len(text)

    def _text(
        self,
        x: float,
        y: float,
        text: str,
        size: int,
        *,
        bold: bool = False,
        italic: bool = False,
        color: str = TEXT_COLOR,
        anchor: str = "start",
        extra: str = "",
    ) -> None:
        weight = ' font-weight="bold"' if bold else ""
        style = ' font-style="italic"' if italic else ""
        escaped = _esc(text)
        self.svg.append(
            f'  <text x="{x:.0f}" y="{y:.0f}" font-family="{self.font_family}" font-size="{size}"'
            f'{weight}{style} fill="{color}" text-anchor="{anchor}"{extra}>{escaped}</text>\n'
        )

    def _rect(
        self, x: float, y: float, w: float, h: float, *, fill: str = "none", stroke: str = "", sw: int = 0
    ) -> None:
        stroke_attr = f' stroke="{stroke}" stroke-width="{sw}"' if stroke else ""
        self.svg.append(
            f'  <rect x="{x:.0f}" y="{y:.0f}" width="{w:.0f}" height="{h:.0f}" fill="{fill}"{stroke_attr}/>\n'
        )

    def _render_cpuinfo(self, top: float) -> float:
        """Draw the excerpt from `top`; return the y just below it."""
        y = top
        highlight_x = float(MARGIN)
        right_edge = WIDTH - MARGIN
        for line in CPUINFO:
            baseline = y + CPUINFO_SIZE
            x = float(MARGIN)
            first_highlight = True
            for span in line.spans:
                w = self._advance(span.text, CPUINFO_SIZE)
                if span.highlight:
                    self._text(x, baseline, span.text, CPUINFO_SIZE, bold=True, color=CE_GREEN)
                    self._rect(x, baseline + HIGHLIGHT_DROP, w, HIGHLIGHT_RULE, fill=CE_GREEN)
                    if first_highlight:
                        highlight_x = x
                        first_highlight = False
                else:
                    self._text(x, baseline, span.text, CPUINFO_SIZE, extra=' xml:space="preserve"')
                x += w
            if line.annotation:
                ann_x = highlight_x if line.under_highlight else max(ANNOTATION_X, x)
                self._text(
                    ann_x, baseline, line.annotation, ANNOTATION_SIZE, italic=True, extra=' xml:space="preserve"'
                )
                x = ann_x + self._width(line.annotation, ANNOTATION_SIZE)
            if x > right_edge:
                overflow = x - right_edge
                self.warnings.append(f"cpuinfo line overflows the right margin by {overflow:.0f}px")
            y += CPUINFO_PITCH
        return y

    def _band_columns(self) -> list[tuple[float, float]]:
        """(x, width) for each band column; the P-only column takes the slack."""
        fixed = sum(BAND_COLUMNS)
        widths = [w or (WIDTH - 2 * MARGIN - fixed) for w in BAND_COLUMNS]
        cols = []
        x = float(MARGIN)
        for w in widths:
            cols.append((x, float(w)))
            x += w
        return cols

    def _cell(
        self,
        cols: list[tuple[float, float]],
        first: int,
        last: int,
        top: float,
        text: str,
        *,
        bold: bool = False,
        color: str = TEXT_COLOR,
        align: str = "start",
    ) -> None:
        """Draw text in columns first..last (inclusive) of a band row, warning if it doesn't fit."""
        if not text:
            return
        x0 = cols[first][0]
        width = cols[last][0] + cols[last][1] - x0
        room = width - 2 * CELL_PAD
        needed = self._width(text, BAND_SIZE, bold)
        if needed > room:
            overflow = needed - room
            self.warnings.append(f"'{text}' is {overflow:.0f}px too wide for its cell")
        baseline = top + BAND_SIZE
        if align == "middle":
            x = x0 + width / 2
        elif align == "end":
            x = x0 + width - CELL_PAD
        else:
            x = x0 + CELL_PAD
        self._text(x, baseline, text, BAND_SIZE, bold=bold, color=color, anchor=align)

    def _render_block(self, cols: list[tuple[float, float]], rows: list[CoreRow], top: float) -> float:
        """Draw one vendor's rows, regions first so text sits on top; return the y below."""
        bottom = top + len(rows) * BAND_PITCH
        p_x = cols[1][0]
        p_w = cols[3][0] + cols[3][1] - p_x
        self._rect(p_x, top, p_w, bottom - top, fill=P_TINT)

        e_rows = [i for i, row in enumerate(rows) if row.e_core]
        e_first = min(e_rows) if e_rows else len(rows)
        e_last = max(e_rows) if e_rows else -1
        if e_rows:
            e_x = cols[3][0]
            e_w = cols[5][0] + cols[5][1] - e_x
            e_top = top + e_first * BAND_PITCH + 1
            e_h = (e_last - e_first + 1) * BAND_PITCH - 2
            self._rect(e_x, e_top, e_w, e_h, stroke=TEXT_COLOR, sw=REGION_RULE)

        for i, row in enumerate(rows):
            row_top = top + i * BAND_PITCH
            # Outside the E outline, P-only text may run on into the empty overlap column.
            p_only_last = 2 if e_first <= i <= e_last else 3
            self._cell(cols, 0, 0, row_top, row.gen, bold=True)
            self._cell(cols, 1, 1, row_top, row.p_core, bold=True, color=CE_GREEN)
            self._cell(cols, 2, p_only_last, row_top, row.p_only)
            self._cell(cols, 3, 3, row_top, row.hybrid, bold=True, align="middle")
            self._cell(cols, 4, 4, row_top, row.e_only)
            self._cell(cols, 5, 5, row_top, row.e_core, bold=True, color=CE_GREEN, align="end")
        return bottom

    def _render_band(self, top: float) -> float:
        cols = self._band_columns()
        # Two staggered header lines: each set's label sits over its own region.
        first_baseline = top + BAND_HEADER_SIZE
        self._text(cols[0][0] + CELL_PAD, first_baseline, "gen", BAND_HEADER_SIZE, bold=True)
        self._text(
            cols[1][0] + CELL_PAD, first_baseline, "P-core ── and chips built on it", BAND_HEADER_SIZE, bold=True
        )
        right = WIDTH - MARGIN - CELL_PAD
        second_baseline = first_baseline + BAND_PITCH
        self._text(right, second_baseline, "chips built on it ── and E-core", BAND_HEADER_SIZE, bold=True, anchor="end")

        y = top + 2 * BAND_PITCH
        y = self._render_block(cols, INTEL, y)
        self._rect(MARGIN, y - REGION_RULE / 2, WIDTH - 2 * MARGIN, REGION_RULE, fill=TEXT_COLOR)
        return self._render_block(cols, AMD, y)

    def _render_key(self, top: float) -> float:
        y = top
        for line in KEY:
            self._text(MARGIN, y + KEY_SIZE, line, KEY_SIZE)
            line_w = self._width(line, KEY_SIZE)
            if MARGIN + line_w > WIDTH - MARGIN:
                self.warnings.append("key line overflows the right margin")
            y += KEY_PITCH
        return y

    def _render_levels(self, top: float) -> float:
        label = "x86-64-"
        label_w = self._width(label, LEVEL_SIZE, bold=True)
        baseline = top + LEVEL_BOX_HEIGHT / 2 + LEVEL_SIZE / 3
        self._text(MARGIN, baseline, label, LEVEL_SIZE, bold=True)
        x = MARGIN + label_w + LEVEL_BOX_GAP
        box_w = (WIDTH - MARGIN - x - LEVEL_BOX_GAP * (len(LEVELS) - 1)) / len(LEVELS)
        for level, flags in LEVELS:
            self._rect(x, top, box_w, LEVEL_BOX_HEIGHT, stroke=TEXT_COLOR, sw=LEVEL_RULE)
            level_w = self._advance(level + " ", LEVEL_SIZE)
            self._text(x + 12, baseline, level, LEVEL_SIZE, bold=True, color=CE_GREEN)
            self._text(x + 12 + level_w, baseline, flags, LEVEL_SIZE)
            needed = 24 + level_w + self._width(flags, LEVEL_SIZE)
            if needed > box_w:
                self.warnings.append(f"x86-64-{level} box is {needed - box_w:.0f}px too narrow")
            x += box_w + LEVEL_BOX_GAP
        return top + LEVEL_BOX_HEIGHT

    def render(self, filename: str, *, generate_png: bool = True, dpi: int = DEFAULT_DPI) -> None:
        self.svg = [
            f'<svg width="{WIDTH}" height="{HEIGHT}" xmlns="http://www.w3.org/2000/svg">\n',
            f'  <rect width="{WIDTH}" height="{HEIGHT}" fill="{BG_COLOR}"/>\n',
        ]
        self.warnings = []
        title_y = MARGIN + TITLE_SIZE
        self._text(WIDTH // 2, title_y, "$ cat /proc/cpuinfo", TITLE_SIZE, bold=True, color=CE_GREEN, anchor="middle")

        y = self._render_cpuinfo(title_y + TITLE_GAP)
        y = self._render_band(y + BAND_GAP)
        y = self._render_key(y + KEY_GAP)
        y = self._render_levels(y + LEVEL_GAP)

        footer_y = HEIGHT - MARGIN + FOOTER_SIZE
        footer_top = footer_y - FOOTER_SIZE
        if y > footer_top:
            overflow = y - footer_top
            self.warnings.append(f"content runs {overflow:.0f}px into the footer")
        self._text(
            WIDTH // 2,
            footer_y,
            "Compiler Explorer",
            FOOTER_SIZE,
            italic=True,
            anchor="middle",
            extra=f' opacity="{FOOTER_OPACITY}"',
        )
        self.svg.append("</svg>\n")
        content = "".join(self.svg)
        Path(filename).write_text(content, encoding="utf-8")

        print(f"SVG created: {filename}  ({WIDTH}x{HEIGHT})")
        for warning in self.warnings:
            print(f"WARNING: {warning}")
        if generate_png:
            try:
                png = svg_to_png(filename, dpi=dpi)
                print(f"PNG created: {png}")
            except RuntimeError as e:
                print(f"Warning: could not create PNG: {e}")


@click.command()
@click.argument("filename", type=click.Path())
@click.option("--no-png", is_flag=True, help="Skip PNG generation")
@click.option("--dpi", default=DEFAULT_DPI, help=f"DPI for PNG generation (default: {DEFAULT_DPI})")
def main(filename: str, no_png: bool, dpi: int) -> None:
    """Generate the /proc/cpuinfo decoder mug design.

    FILENAME is the output SVG file path (required).
    """
    CpuinfoMugRenderer().render(filename, generate_png=not no_png, dpi=dpi)
