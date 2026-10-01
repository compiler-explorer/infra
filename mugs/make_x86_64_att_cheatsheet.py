#!/usr/bin/env python3
"""Generate the x86-64 AT&T-syntax architecture cheat-sheet design for mugs."""

from generators.x86_att import X86AttCheatSheetGenerator

if __name__ == "__main__":
    generator = X86AttCheatSheetGenerator()
    command = generator.get_click_command()
    command()
