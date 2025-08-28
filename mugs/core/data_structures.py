"""Data structures for mug generation."""

from dataclasses import dataclass
from typing import Any

from core.constants import FONT_NAME, TEXT_COLOR


@dataclass
class TextMeasurement:
    width: float
    height: float
    ascent: float = 0.0
    descent: float = 0.0


@dataclass
class ContentBlock:
    content: str
    font_size: int
    font_weight: str = "normal"
    color: str = TEXT_COLOR
    font_family: str = FONT_NAME


@dataclass
class TableRow:
    label: str
    cells: list[str]


@dataclass
class InfoItem:
    label: str
    parts: list[tuple[str, bool]]


@dataclass
class MugLayout:
    title: str
    code_examples: list[str]
    table_headers: list[str]
    table_rows: list[TableRow]
    info_items: list[tuple[str, str]]  # Now (label, content) pairs for info table
    footer_lines: list[str]  # Changed from footer_note to array of lines
    title_size: int
    header_size: int
    text_size: int
    info_text_size: int
    table_row_padding: int  # Vertical padding above/below text in table rows
    footer_spacing: int

    def __post_init__(self) -> None:
        self.measurements: dict[str, Any] = {}
