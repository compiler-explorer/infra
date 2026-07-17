"""RISC-V ABI mug generator."""

from core.constants import (
    RISCV_TABLE_ROW_PADDING,
    STANDARD_FOOTER_SPACING,
    STANDARD_HEADER_SIZE,
    STANDARD_INFO_TEXT_SIZE,
    STANDARD_TEXT_SIZE,
    STANDARD_TITLE_SIZE,
)
from core.data_structures import MugLayout, TableRow

from .base import ABIMugGenerator


class RISCVMugGenerator(ABIMugGenerator):
    """RISC-V ABI mug generator."""

    def get_title(self) -> str:
        return "RISC-V (RV64) ABI"

    def get_layout_data(self) -> MugLayout:
        return MugLayout(
            title=self.get_title(),
            code_examples=[],  # No longer used
            table_headers=["a0", "a1", "a2", "a3", "a4", "a5", "a6", "a7"],  # 8 argument registers
            table_rows=[
                TableRow(label="func()", cells=["1st", "2nd", "3rd", "4th", "5th", "6th", "7th", "8th"]),
                TableRow(label="obj.f()", cells=["this", "1st", "2nd", "3rd", "4th", "5th", "6th", "7th"]),
            ],
            info_items=[
                ("Return values", "a0 (+ a1 for 128-bit)"),
                ("FP args", "fa0-fa7"),
                ("FP return", "fa0 (+ fa1 for 128-bit)"),
                ("Special regs", "ra (x1) link, sp (x2) stack"),
                ("", "fp/s0 (x8) frame"),
                ("Caller-saved", "ra t0-t6 a0-a7"),
                ("", "ft0-ft11"),
                ("Callee-saved", "s0-s11 fs0-fs11"),
            ],
            footer_lines=["Args beyond 8 int/FP args on stack (16b aligned)"],
            title_size=STANDARD_TITLE_SIZE,
            header_size=STANDARD_HEADER_SIZE,
            text_size=STANDARD_TEXT_SIZE,
            info_text_size=STANDARD_INFO_TEXT_SIZE,
            table_row_padding=RISCV_TABLE_ROW_PADDING,
            footer_spacing=STANDARD_FOOTER_SPACING,
        )


if __name__ == "__main__":
    generator = RISCVMugGenerator()
    command = generator.get_click_command()
    command()
