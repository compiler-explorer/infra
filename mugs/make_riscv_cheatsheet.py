#!/usr/bin/env python3
"""Generate the RISC-V (RV64) architecture cheat-sheet design for mugs."""

from generators.riscv_isa import RiscVCheatSheetGenerator

if __name__ == "__main__":
    generator = RiscVCheatSheetGenerator()
    command = generator.get_click_command()
    command()
