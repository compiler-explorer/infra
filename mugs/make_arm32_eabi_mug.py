#!/usr/bin/env python3
"""Generate ARM32 EABI reference design for mugs using the new generator system."""

from generators.arm32_eabi import ARM32EABIMugGenerator

if __name__ == "__main__":
    generator = ARM32EABIMugGenerator()
    command = generator.get_click_command()
    command()
