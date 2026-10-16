#!/usr/bin/env python3
"""Generate the x86-64 Intel-syntax architecture cheat-sheet design for mugs."""

from generators.x86_intel import X86IntelCheatSheetGenerator

if __name__ == "__main__":
    generator = X86IntelCheatSheetGenerator()
    command = generator.get_click_command()
    command()
