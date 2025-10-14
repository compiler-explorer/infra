#!/usr/bin/env python3
"""Generate ARM64 (AAPCS) ABI reference design for mugs using the new generator system."""

from generators.arm64 import ARM64MugGenerator

if __name__ == "__main__":
    generator = ARM64MugGenerator()
    command = generator.get_click_command()
    command()
