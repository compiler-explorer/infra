#!/usr/bin/env python3
"""Generate the /proc/cpuinfo decoder design for mugs."""

from generators.cpuinfo import CpuinfoGenerator

if __name__ == "__main__":
    generator = CpuinfoGenerator()
    command = generator.get_click_command()
    command()
