#!/usr/bin/env python3
"""Generate ARM64 Go ABI reference design for mugs using the new generator system."""

from generators.go import RiscvMugGenerator

if __name__ == "__main__":
    generator = RiscvMugGenerator()
    command = generator.get_click_command()
    command()
