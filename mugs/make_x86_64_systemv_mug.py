#!/usr/bin/env python3
"""Generate x86-64 System V ABI reference design for mugs using the new generator system."""

from generators.systemv import SystemVMugGenerator

if __name__ == "__main__":
    generator = SystemVMugGenerator()
    command = generator.get_click_command()
    command()
