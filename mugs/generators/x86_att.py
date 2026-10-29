"""x86-64 (AT&T / GAS syntax) architecture cheat-sheet generator."""

from core.cheatsheet import Block, CheatSheet, DiagramBar, RegDiagram, green, plain

from .cheatsheet_base import CheatSheetGenerator


class X86AttCheatSheetGenerator(CheatSheetGenerator):
    """x86-64 AT&T-syntax cheat sheet."""

    def get_cheatsheet(self) -> CheatSheet:
        # Same sub-register nesting as Intel, but AT&T spells registers in
        # lower case with a % sigil.
        registers = RegDiagram(
            heading="Registers",
            bars=[
                DiagramBar(bits="64", fraction=1.0, segments=["%rax"]),
                DiagramBar(bits="32", fraction=0.5, segments=["%eax"]),
                DiagramBar(bits="16", fraction=0.25, segments=["%ax"]),
                DiagramBar(bits="8", fraction=0.25, segments=["%ah", "%al"]),
            ],
            notes=[
                "+ rbx rcx rdx rsi rdi rbp rsp r8-r15",
                "eax write zero-extends; ax/al don't",
            ],
        )

        # AT&T-specific syntax is the whole point of this mug.
        syntax = Block(
            heading="Syntax",
            rows=[
                [green("op src, dst"), plain("source FIRST")],
                [green("%rax  $42"), plain("% reg, $ imm/address")],
                [green("movb/w/l/q"), plain("suffix = 8/16/32/64")],
                [green("d(b,i,s)"), plain("disp(base,index,scale)")],
                [green("x(%rip)"), plain("RIP-relative")],
                [green("jmp *%rax"), plain("* = indirect")],
            ],
        )

        instructions = Block(
            heading="Instructions",
            rows=[
                [green("movz/movs"), plain("widen: movzbl movslq")],
                [green("lea"), plain("address calc / arith")],
                [green("imul"), plain("multiply (u or s)")],
                [green("div/idiv"), plain("quot %rax, rem %rdx")],
                [green("cltd/cqto"), plain("sign-extend for idiv")],
                [green("and/or/xor"), plain("bitwise")],
                [green("shl/shr/sar"), plain("L/R/arith-R (sal=shl)")],
                [green("cmp / test"), plain("flags: dst-src, dst&src")],
                [green("setcc/cmovcc"), plain("set byte / mov if cc")],
                [green("(u)comisd"), plain("float cmp: then b/a cc")],
                [green("addss/sd"), plain("scalar float / double")],
                [green("addps/pd"), plain("packed float / double")],
                [green("vaddps"), plain("AVX: 3-op, ymm/zmm")],
            ],
            notes=["+ mov add sub jmp call ret push pop"],
        )

        # In AT&T operand order, cmp b,a computes a-b, so jl below means a<b.
        flags = Block(
            heading="Flags & cc (after cmp b,a)",
            rows=[
                [green("e/z"), plain("=="), green("ne/nz"), plain("!=")],
                [green("l  g"), plain("< > signed"), green("b  a"), plain("< > unsigned")],
                [green("le ge"), plain("<= >="), green("be ae"), plain("<= >=")],
            ],
            notes=["ZF zero SF sign CF carry OF overflow"],
        )

        idioms = Block(
            heading="Idioms",
            rows=[
                [green("zero reg"), plain("xorl %eax,%eax")],
                [green("zero xmm"), plain("pxor %xmm0,%xmm0")],
                [green("is zero?"), plain("testl %eax,%eax")],
                [green("divide"), plain("(i)mul+shr by magic #")],
                [green("int→dbl"), plain("cvtsi2sd(l)")],
                [green("dbl→int"), plain("cvttsd2si(l) truncs")],
            ],
        )

        return CheatSheet(
            title="x86-64  AT&T syntax",
            columns=[
                [instructions, idioms],
                [registers, syntax, flags],
            ],
            footer="Compiler Explorer",
        )


if __name__ == "__main__":
    generator = X86AttCheatSheetGenerator()
    command = generator.get_click_command()
    command()
