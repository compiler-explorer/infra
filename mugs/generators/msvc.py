"""MSVC ABI mug generator."""

from core.constants import (
    MSVC_TABLE_ROW_PADDING,
    STANDARD_FOOTER_SPACING,
    STANDARD_HEADER_SIZE,
    STANDARD_INFO_TEXT_SIZE,
    STANDARD_TEXT_SIZE,
    STANDARD_TITLE_SIZE,
)
from core.data_structures import MugLayout, TableRow

from .base import ABIMugGenerator


class MSVCMugGenerator(ABIMugGenerator):
    """MSVC ABI mug generator."""

    def get_title(self) -> str:
        return "x86-64 Windows (MSVC) ABI"

    def get_layout_data(self) -> MugLayout:
        return MugLayout(
            title=self.get_title(),
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
            title_size=STANDARD_TITLE_SIZE,
            header_size=STANDARD_HEADER_SIZE,
            text_size=STANDARD_TEXT_SIZE,
            info_text_size=STANDARD_INFO_TEXT_SIZE,
            table_row_padding=MSVC_TABLE_ROW_PADDING,  # Padding above/below text in table rows
            footer_spacing=STANDARD_FOOTER_SPACING,
        )


if __name__ == "__main__":
    generator = MSVCMugGenerator()
    command = generator.get_click_command()
    command()
