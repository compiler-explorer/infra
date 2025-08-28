"""ARM32 EABI mug generator."""

from core.constants import (
    ARM32_EABI_TABLE_ROW_PADDING,
    STANDARD_FOOTER_SPACING,
    STANDARD_HEADER_SIZE,
    STANDARD_INFO_TEXT_SIZE,
    STANDARD_TEXT_SIZE,
    STANDARD_TITLE_SIZE,
)
from core.data_structures import MugLayout, TableRow

from .base import ABIMugGenerator


class ARM32EABIMugGenerator(ABIMugGenerator):
    """ARM32 EABI mug generator."""

    def get_title(self) -> str:
        return "ARM32 EABI"

    def get_layout_data(self) -> MugLayout:
        return MugLayout(
            title=self.get_title(),
            code_examples=[],  # No longer used
            table_headers=["R0", "R1", "R2", "R3"],  # 4 registers for integer args
            table_rows=[
                TableRow(label="func()", cells=["1st", "2nd", "3rd", "4th"]),
                TableRow(label="obj.f()", cells=["this", "1st", "2nd", "3rd"]),
            ],
            info_items=[
                ("Return values", "R0 (+ R1 for 64-bit)"),
                ("Special regs", "R11 FP, R12 IP"),
                ("", "R13 SP, R14 LR, R15 PC"),
                ("VFP args", "S0-S15 (D0-D7)"),
                ("VFP return", "S0 (D0)"),
                ("Caller-saved", "R0-R3, R12"),
                ("Callee-saved", "R4-R11"),
                ("", "(R13-R15 special)"),
            ],
            footer_lines=["Args beyond 4 int or 16 VFP args on stack (8b aligned)"],
            title_size=STANDARD_TITLE_SIZE,
            header_size=STANDARD_HEADER_SIZE,
            text_size=STANDARD_TEXT_SIZE,
            info_text_size=STANDARD_INFO_TEXT_SIZE,
            table_row_padding=ARM32_EABI_TABLE_ROW_PADDING,
            footer_spacing=STANDARD_FOOTER_SPACING,
        )


if __name__ == "__main__":
    generator = ARM32EABIMugGenerator()
    command = generator.get_click_command()
    command()
