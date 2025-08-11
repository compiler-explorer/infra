#!/usr/bin/env python3
"""Generate x86-64 Windows (MSVC) ABI reference design for mugs using the new generator system."""

from generators.msvc import MSVCMugGenerator

if __name__ == "__main__":
    generator = MSVCMugGenerator()
    command = generator.get_click_command()
    command()
