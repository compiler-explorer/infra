"""AArch64 (ARM64) architecture cheat-sheet generator."""

from core.cheatsheet import Block, CheatSheet, DiagramBar, RegDiagram, green, plain

from .cheatsheet_base import CheatSheetGenerator


class AArch64CheatSheetGenerator(CheatSheetGenerator):
    """AArch64 cheat sheet, tuned for reading GCC/Clang output."""

    def get_cheatsheet(self) -> CheatSheet:
        # Same idea as the x86 diagram: Wn is the low half of Xn, and writing it
        # zeroes the top, which is why int->long needs an explicit sxtw.
        registers = RegDiagram(
            heading="Registers",
            bars=[
                DiagramBar(bits="64", fraction=1.0, segments=["X0"]),
                DiagramBar(bits="32", fraction=0.5, segments=["W0"]),
            ],
            notes=[
                "X0-7 args, X0 ret; X19-28 saved",
                "W write zeroes the top 32 bits",
                "X29 fp, X30 lr, SP; XZR reads 0",
                "V0-31 as Q128 D64 S32 H16 B8",
            ],
        )

        syntax = Block(
            heading="Syntax",
            rows=[
                [green("op d, a, b"), plain("dest first")],
                [green("#42"), plain("imm (gcc mostly no #)")],
                [green("[x0, 8]"), plain("x0 + 8")],
                [green("[x0, 8]!"), plain("pre: x0 += 8 first")],
                [green("[x0], 8"), plain("post: x0 += 8 after")],
                [green("[x0,w1,sxtw 3]"), plain("x0 + sext(w1)*8")],
            ],
        )

        instructions = Block(
            heading="Instructions",
            rows=[
                [green("mov/movk"), plain("k: set 16b, keep rest")],
                [green("ldr/str"), plain("load / store")],
                [green("ldrsb/ldrh"), plain("s=sign-ext, else zero")],
                [green("ldp/stp"), plain("load / store a pair")],
                [green("cmp/tst"), plain("subs/ands to xzr")],
                [green("madd/msub"), plain("c + a*b / c - a*b")],
                [green("sdiv/udiv"), plain("divide, no remainder")],
                [green("lsl/lsr/asr"), plain("shift L / R / arith-R")],
                [green("orr/eor/bic"), plain("or / xor / and-not")],
                [green("sxtw/uxtw"), plain("sign/zero ext; mov w,w")],
                [green("csel/cset"), plain("pick / bool if cc")],
                [green("cb(n)z tb(n)z"), plain("if 0 / if bit n is 0")],
                [green("fmadd"), plain("fused c + a*b")],
                [green("scvtf/fcvtzs"), plain("int → fp / fp → int")],
            ],
            notes=["+ add sub mul and b bl blr ret"],
        )

        flags = Block(
            heading="Flags & cc (after cmp a,b)",
            rows=[
                [green("eq"), plain("=="), green("ne"), plain("!=")],
                [green("lt gt"), plain("< > signed"), green("lo hi"), plain("< > unsigned")],
                [green("le ge"), plain("<= >="), green("ls hs"), plain("<= >=")],
            ],
            notes=["gcc: blt=b.lt bcc=b.lo bcs=b.hs", "fcmp(e): < is mi, <= is ls"],
        )

        idioms = Block(
            heading="Idioms",
            rows=[
                [green("adrp+:lo12:"), plain("address of a global")],
                [green("stp x29,x30"), plain("frame push; ldp pops")],
                [green("sdiv+msub"), plain("a % b")],
                [green("umul(l/h)+lsr"), plain("divide by constant")],
                [green("b fn"), plain("tail call, no ret back")],
            ],
        )

        return CheatSheet(
            title="AArch64 (ARM64)",
            columns=[
                [instructions, idioms],
                [registers, syntax, flags],
            ],
            footer="Compiler Explorer",
        )


if __name__ == "__main__":
    generator = AArch64CheatSheetGenerator()
    command = generator.get_click_command()
    command()
