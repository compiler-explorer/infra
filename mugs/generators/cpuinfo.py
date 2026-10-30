"""/proc/cpuinfo decoder mug: identify a CPU from vendor, family and model numbers.

model name is marketing, and VMs often hide it ("AMD EPYC Processor"), so the
lookup keys on the numeric fields instead. Intel rows are sorted by model number
so you can scan for yours.
"""

from core.cheatsheet import Block, Cell, CheatSheet, green, plain

from .cheatsheet_base import CheatSheetGenerator


def row(models: str, core: str, chips: str) -> list[Cell]:
    return [green(models), plain(core), plain(chips)]


class CpuinfoGenerator(CheatSheetGenerator):
    """Decoder chart keyed on cpuinfo's numeric fields."""

    def get_cheatsheet(self) -> CheatSheet:
        decode = Block(
            heading="Decode",
            rows=[
                [green("1 vendor_id"), plain("GenuineIntel/AuthenticAMD")],
                [green("2 cpu family"), plain("Intel 6, soon 18/19")],
                [green("3 model"), plain("decimal: find it below")],
                [green("4 flags"), plain("avx2 = v3, avx512* = v4")],
            ],
            notes=["model name: marketing, VMs hide it"],
        )
        # Model numbers from the kernel's arch/x86/include/asm/intel-family.h.
        intel_a = Block(
            heading="Intel family 6",
            rows=[
                row("60 63 69 70", "Haswell", "client, EP"),
                row("61 71 79 86", "Broadwell", "client, EP"),
                row("78 94", "Skylake", "client"),
                row("85", "Skylake", "Xeon, Core-X"),
                row("85 +vnni", "Skylake", "Cascade Lake"),
                row("106 108", "Sunny Cove", "Ice Lake-SP"),
                row("125 126", "Sunny Cove", "Ice Lake"),
                row("140 141", "Willow Cove", "Tiger Lake"),
                row("142 158", "Skylake", "Kaby Coffee"),
                row("143", "Golden Cove", "Sapphire R."),
            ],
        )
        intel_b = Block(
            heading="Intel family 6, cont.",
            rows=[
                row("151 154", "Golden Cove", "Alder Lake*"),
                row("165 166", "Skylake", "Comet Lake"),
                row("167", "Cypress Cove", "Rocket Lake"),
                row("170 172", "Redwood Cove", "Meteor Lake*"),
                row("173 174", "Redwood Cove", "Granite R."),
                row("175", "Crestmont", "Sierra Forest"),
                row("181", "Redwood Cove", "Arrow Lake-U*"),
                row("183 186 191", "Raptor Cove", "Raptor Lake*"),
                row("189", "Lion Cove", "Lunar Lake*"),
                row("190", "Gracemont", "Alder Lake-N"),
                row("197 198", "Lion Cove", "Arrow Lake*"),
                row("204", "Cougar Cove", "Panther Lake*"),
                row("207", "Raptor Cove", "Emerald R."),
                row("221", "Darkmont", "Clearwater F."),
            ],
            notes=["* hybrid (+ E-cores)"],
        )
        # Zen generation ranges from the kernel's arch/x86/kernel/cpu/amd.c.
        amd = Block(
            heading="AMD family · model",
            rows=[
                row("23 · <48", "Zen, Zen+", "Naples 1"),
                row("23 · 48+", "Zen 2", "Rome 49"),
                row("25 · <16 32-95", "Zen 3", "Milan 1"),
                row("25 · 16-31 96+", "Zen 4", "Genoa 17"),
                row("26 · <80 96-127", "Zen 5", "Turin 2"),
                row("26 · 80-95 128+", "Zen 6", "Venice"),
            ],
        )
        # Arm cores report no model name, only implementer and part codes (hex);
        # values from the kernel's arch/arm64/include/asm/cputype.h.
        arm = Block(
            heading="ARM64 · CPU part",
            rows=[
                row("0xd08", "Cortex-A72", "Graviton1, Pi 4"),
                row("0xd0c", "Neoverse N1", "Graviton2, Altra"),
                row("0xd40", "Neoverse V1", "Graviton3"),
                row("0xd4f", "Neoverse V2", "Graviton4, Grace"),
            ],
        )
        return CheatSheet(
            title="$ cat /proc/cpuinfo",
            columns=[[decode, intel_a, arm], [intel_b, amd]],
            footer="Compiler Explorer",
        )


if __name__ == "__main__":
    generator = CpuinfoGenerator()
    command = generator.get_click_command()
    command()
