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


class X86MugGenerator(ABIMugGenerator):
    """x86 Go mug generator."""

    def get_title(self) -> str:
        return "x86-64 Go ABI"

    def get_layout_data(self) -> MugLayout:
        return MugLayout(
            title=self.get_title(),
            code_examples=[],  # No longer used
            table_headers=["AX", "BX", "CX", "DI", "SI", "R8", "R9", "R10", "R11"],  # Register names
            table_rows=[
                TableRow(label="Func()", cells=["1st", "2nd", "3rd", "4th", "5th", "6th", "7th", "8th", "9th"]),  # Function parameters
                TableRow(label="v.Fn()", cells=["v", "1st", "2nd", "3rd", "4th", "5th", "6th", "7th", "8th"]),  # Member parameters
            ],
            info_items=[
                ("Return values", "Same as arguments"),
                ("FP args", "X0-X14, X15 is zero"),
                ("FP return", "Same as arguments"),
                ("Closure pointer", "DX"),
                ("Scratch", "R12 R13 R15"),
                ("Current G", "R14"),
            ],
            footer_lines=["Args beyond 9 int or 15 FP args passed on the stack"],
            title_size=STANDARD_TITLE_SIZE,
            header_size=STANDARD_HEADER_SIZE,
            text_size=STANDARD_TEXT_SIZE,
            info_text_size=STANDARD_INFO_TEXT_SIZE,
            table_row_padding=SYSTEMV_TABLE_ROW_PADDING,  # Padding above/below text in table rows
            footer_spacing=STANDARD_FOOTER_SPACING,
        )
    
class ArmMugGenerator(ABIMugGenerator):
    """Arm Go mug generator."""

    def get_title(self) -> str:
        return "ARM64 Go ABI"

    def get_layout_data(self) -> MugLayout:
        return MugLayout(
            title=self.get_title(),
            code_examples=[],  # No longer used
            table_headers=["R0", "R1", "R2", "R3", "...", "R12", "R13", "R14", "R15"],  # Register names
            table_rows=[
                TableRow(label="Func()", cells=["1st", "2nd", "3rd", "4th", "...", "13th", "14th", "15th", "16th"]),  # Function parameters
                TableRow(label="v.Fn()", cells=["v", "1st", "2nd", "3rd", "...", "12th", "13th", "14th", "15th"]),  # Member parameters
            ],
            info_items=[
                ("Return values", "Same as arguments"),
                ("Special regs", "R30 link, RSP stack"),
                ("", "R18 reserved"),
                ("FP args", "F0-F15"),
                ("FP return", "Same as arguments"),
                ("Closure pointer", "R26"),
                ("Scratch", "R19-R25, R27"),
                ("", "F16-F31"),
                ("Current G", "R28"),
            ],
            footer_lines=["Args beyond 16 int/FP args passed on the stack"],
            title_size=STANDARD_TITLE_SIZE,
            header_size=STANDARD_HEADER_SIZE,
            text_size=STANDARD_TEXT_SIZE,
            info_text_size=STANDARD_INFO_TEXT_SIZE,
            table_row_padding=SYSTEMV_TABLE_ROW_PADDING,  # Padding above/below text in table rows
            footer_spacing=STANDARD_FOOTER_SPACING,
        )
    
class RiscvMugGenerator(ABIMugGenerator):
    """Riscv Go mug generator."""

    def get_title(self) -> str:
        return "RISC-V (RV64) Go ABI"

    def get_layout_data(self) -> MugLayout:
        return MugLayout(
            title=self.get_title(),
            code_examples=[],  # No longer used
            table_headers=["X10", "X11", "...", "X17", "X8", "X9", "X18", "...", "X23"],  # Register names
            table_rows=[
                TableRow(label="Func()", cells=["1st", "2nd", "...", "8th", "9th", "10th", "11th", "...", "16th"]),  # Function parameters
                TableRow(label="v.Fn()", cells=["v", "1st", "...", "7th", "8th", "9th", "10th", "...", "15th"]),  # Member parameters
            ],
            info_items=[
                ("Return values", "Same as arguments"),
                ("Special regs", "X0 zero, X1 link"),
                ("", "X2 stack"),
                ("FP args", "F10-F17 F8 F9 F18-F23"),
                ("FP return", "Same as arguments"),
                ("Closure pointer", "X26"),
                ("Scratch", "X24 X25 X31"),
                ("Current G", "X26"),
            ],
            footer_lines=["Args beyond 16 int/FP args passed on the stack"],
            title_size=STANDARD_TITLE_SIZE,
            header_size=STANDARD_HEADER_SIZE,
            text_size=STANDARD_TEXT_SIZE,
            info_text_size=STANDARD_INFO_TEXT_SIZE,
            table_row_padding=SYSTEMV_TABLE_ROW_PADDING,  # Padding above/below text in table rows
            footer_spacing=STANDARD_FOOTER_SPACING,
        )