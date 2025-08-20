#!/usr/bin/env python3
"""Generate RISC-V ABI reference design for mugs using the new generator system."""

from generators.riscv import RISCVMugGenerator

if __name__ == "__main__":
    generator = RISCVMugGenerator()
    command = generator.get_click_command()
    command()
