"""RISC-V (RV64) architecture cheat-sheet generator."""

from core.cheatsheet import Block, CheatSheet, green, plain

from .cheatsheet_base import CheatSheetGenerator


class RiscVCheatSheetGenerator(CheatSheetGenerator):
    """RV64GC cheat sheet, tuned for reading GCC/Clang output."""

    def get_cheatsheet(self) -> CheatSheet:
        # Compiler output only ever shows ABI names (a0, s0), never x10/x8, so
        # unlike the x86/ARM mugs the register block has to be the name map.
        registers = Block(
            heading="Registers",
            rows=[
                [green("zero"), plain("x0, always 0")],
                [green("ra sp"), plain("return addr, stack")],
                [green("a0-a7"), plain("args; a0 = result")],
                [green("t0-t6"), plain("temporaries")],
                [green("s0-s11"), plain("saved; s0 = fp")],
                [green("fa ft fs"), plain("float, same roles")],
            ],
            notes=["32-bit values sign-ext, even u32"],
        )

        syntax = Block(
            heading="Syntax",
            rows=[
                [green("op rd, a, b"), plain("dest first (not st/br)")],
                [green("8(sp)"), plain("offset(base) only")],
                [green("%hi %lo"), plain("hi20/lo12 (non-PIE)")],
                [green("%pcrel_hi"), plain("PC-rel (PIE, clang)")],
                [green("fadd.d .s"), plain("double / single")],
                [green("fcvt.w.d"), plain("to.from; rtz = trunc")],
            ],
        )

        instructions = Block(
            heading="Instructions",
            rows=[
                [green("li / mv"), plain("load imm / copy")],
                [green("lui/auipc"), plain("imm<<12 (+pc)")],
                [green("addi"), plain("add imm (no subi)")],
                [green("*w, sext.w"), plain("32-bit op, sign-ext")],
                [green("ld/lw/lh/lb"), plain("load 64/32/16/8")],
                [green("lwu lhu lbu"), plain("u = zero-extend")],
                [green("sd/sw/sh/sb"), plain("store")],
                [green("sll srl sra"), plain("shift; i = imm")],
                [green("j / jr ra"), plain("jump / return (gcc)")],
                [green("mulh(u)"), plain("high half of a*b")],
                [green("div/rem(u)"), plain("divide / remainder")],
                [green("slt(u)"), plain("bool: a < b")],
                [green("seqz/snez"), plain("bool: ==0 / !=0")],
                [green("call/tail"), plain("call / tail jump")],
            ],
            notes=["+ add sub mul and or xor not neg ret"],
        )

        # No flags register: every compare is folded into its branch.
        branches = Block(
            heading="Branches (no flags!)",
            rows=[
                [green("beq bne"), plain("== !=")],
                [green("blt bge"), plain("< >= signed")],
                [green("bltu bgeu"), plain("< >= unsigned")],
                [green("b..z"), plain("beqz bnez blez..")],
            ],
            notes=["bgt ble(u): swapped blt bge"],
        )

        idioms = Block(
            heading="Idioms",
            rows=[
                [green("bne a,zero"), plain("gcc spells b..z out")],
                [green("slli+srli 32"), plain("zero-extend u32")],
                [green("andi 0xff"), plain("zero-extend u8")],
                [green("mul(hu)+srli"), plain("divide by constant")],
                [green("addi sp,sp,-N"), plain("frame; sd ra,N(sp)")],
            ],
        )

        return CheatSheet(
            title="RISC-V (RV64)",
            columns=[
                [instructions, idioms],
                [registers, syntax, branches],
            ],
            footer="Compiler Explorer",
        )


if __name__ == "__main__":
    generator = RiscVCheatSheetGenerator()
    command = generator.get_click_command()
    command()
