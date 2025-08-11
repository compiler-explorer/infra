"""ARM64 ABI mug generator."""

from core.constants import (
    ARM64_TABLE_ROW_PADDING,
    STANDARD_FOOTER_SPACING,
    STANDARD_HEADER_SIZE,
    STANDARD_INFO_TEXT_SIZE,
    STANDARD_TEXT_SIZE,
    STANDARD_TITLE_SIZE,
)
from core.data_structures import MugLayout, TableRow

from .base import ABIMugGenerator


class ARM64MugGenerator(ABIMugGenerator):
    """ARM64 ABI mug generator."""

    def get_title(self) -> str:
        return "ARM64 (AAPCS) ABI"

    def get_layout_data(self) -> MugLayout:
        return MugLayout(
            title=self.get_title(),
            code_examples=[],  # No longer used
            table_headers=["X0", "X1", "X2", "X3", "X4", "X5", "X6", "X7"],  # 8 registers
            table_rows=[
                TableRow(cells=["1st", "2nd", "3rd", "4th", "5th", "6th", "7th", "8th"]),
                TableRow(cells=["this", "1st", "2nd", "3rd", "4th", "5th", "6th", "7th"]),
            ],
            info_items=[
                ("Return values", "X0 (+ X1 for 128-bit)"),
                ("Special regs", "X8 indirect, X29 FP"),
                ("", "X30 LR, SP stack"),
                ("FP args", "V0-V7"),
                ("FP return", "V0 (+ V1 for 128-bit)"),
                ("Caller-saved", "X0-X17 V0-V7 V16-V31"),
                ("Callee-saved", "X19-X28 V8-V15"),
                ("", "(lower 64 bits)"),
            ],
            footer_lines=["Parameters beyond 8 int/FP args on stack (16-byte aligned)"],
            title_size=STANDARD_TITLE_SIZE,
            header_size=STANDARD_HEADER_SIZE,
            text_size=STANDARD_TEXT_SIZE,
            info_text_size=STANDARD_INFO_TEXT_SIZE,
            table_row_padding=ARM64_TABLE_ROW_PADDING,  # Padding above/below text in table rows
            footer_spacing=STANDARD_FOOTER_SPACING,
        )


if __name__ == "__main__":
    generator = ARM64MugGenerator()
    command = generator.get_click_command()
    command()
