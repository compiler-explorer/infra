#!/usr/bin/env python3
"""Generate the AArch64 (ARM64) architecture cheat-sheet design for mugs."""

from generators.aarch64_isa import AArch64CheatSheetGenerator

if __name__ == "__main__":
    generator = AArch64CheatSheetGenerator()
    command = generator.get_click_command()
    command()
