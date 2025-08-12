"""System V ABI mug generator."""

from core.constants import (
    STANDARD_FOOTER_SPACING,
    STANDARD_HEADER_SIZE,
    STANDARD_INFO_TEXT_SIZE,
    STANDARD_TEXT_SIZE,
    STANDARD_TITLE_SIZE,
    SYSTEMV_TABLE_ROW_PADDING,
)
from core.data_structures import MugLayout, TableRow

from .base import ABIMugGenerator


class SystemVMugGenerator(ABIMugGenerator):
    """System V ABI mug generator."""

    def get_title(self) -> str:
        return "x86-64 System V ABI"

    def get_layout_data(self) -> MugLayout:
        return MugLayout(
            title=self.get_title(),
            code_examples=[],  # No longer used
            table_headers=["RDI", "RSI", "RDX", "RCX", "R8", "R9"],  # Register names
            table_rows=[
                TableRow(["1st", "2nd", "3rd", "4th", "5th", "6th"]),  # Function parameters
                TableRow(["this", "1st", "2nd", "3rd", "4th", "5th"]),  # Member parameters
            ],
            info_items=[
                ("Return values", "RAX (+ RDX for 128-bit)"),
                ("FP args", "XMM0-XMM7"),
                ("FP return", "XMM0 (+ XMM1 for 128-bit)"),
                ("Caller-saved", "RAX RCX RDX RSI RDI"),
                ("", "R8-R11 XMM0-XMM15"),
                ("Callee-saved", "RBX RBP R12-R15"),
            ],
            footer_lines=["Args beyond 6 int or 8 FP args passed on the stack"],
            title_size=STANDARD_TITLE_SIZE,
            header_size=STANDARD_HEADER_SIZE,
            text_size=STANDARD_TEXT_SIZE,
            info_text_size=STANDARD_INFO_TEXT_SIZE,
            table_row_padding=SYSTEMV_TABLE_ROW_PADDING,  # Padding above/below text in table rows
            footer_spacing=STANDARD_FOOTER_SPACING,
        )


if __name__ == "__main__":
    generator = SystemVMugGenerator()
    command = generator.get_click_command()
    command()
