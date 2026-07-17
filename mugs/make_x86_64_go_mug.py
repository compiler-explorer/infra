#!/usr/bin/env python3
"""Generate x86-64 Go ABI reference design for mugs using the new generator system."""

from generators.go import X86MugGenerator

if __name__ == "__main__":
    generator = X86MugGenerator()
    command = generator.get_click_command()
    command()
