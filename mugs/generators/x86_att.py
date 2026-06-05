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
                "32-bit write zero-extends; 8/16 don't",
            ],
        )

        # AT&T-specific syntax is the whole point of this mug.
        syntax = Block(
            heading="Syntax",
            rows=[
                [green("op src, dst"), plain("source FIRST")],
                [green("%rax  $42"), plain("% reg, $ immediate")],
                [green("movb/w/l/q"), plain("suffix = 8/16/32/64")],
                [green("d(b,i,s)"), plain("disp(base,index,scale)")],
                [green("jmp *%rax"), plain("* = indirect")],
            ],
        )

        instructions = Block(
            heading="Instructions",
            rows=[
                [green("mov"), plain("copy (+ size suffix)")],
                [green("movz/movs"), plain("widen: zero / sign")],
                [green("lea"), plain("address calc / arith")],
                [green("add/sub"), plain("add / subtract")],
                [green("imul"), plain("signed multiply")],
                [green("idiv"), plain("signed div %rdx:%rax")],
                [green("cltd/cqto"), plain("sign-extend for idiv")],
                [green("and/or/xor"), plain("bitwise  (xor r,r=0)")],
                [green("shl/shr/sar"), plain("shift L / R / arith-R")],
                [green("cmp / test"), plain("flags: a-b / a&b")],
                [green("setcc"), plain("set byte on cond")],
                [green("cmovcc"), plain("conditional move")],
                [green("jmp / jcc"), plain("jump / conditional")],
                [green("call / ret"), plain("call / return")],
                [green("push / pop"), plain("stack (pushq/popq)")],
                [green("endbr64"), plain("CET pad (fn entry)")],
            ],
        )

        flags = Block(
            heading="Flags & Jcc",
            rows=[
                [green("ZF"), plain("zero"), green("CF"), plain("carry")],
                [green("SF"), plain("sign"), green("OF"), plain("overflow")],
                [green("je/jz"), plain("a==b"), green("jne"), plain("a!=b")],
                [green("jl jle"), plain("signed <"), green("jg jge"), plain("signed >")],
                [green("jb jbe"), plain("unsigned <"), green("ja jae"), plain("unsigned >")],
            ],
        )

        idioms = Block(
            heading="Idioms",
            rows=[
                [green("zero reg"), plain("xorl %eax,%eax")],
                [green("lea"), plain("multiply + add, no flags")],
                [green("endian"), plain("44 33 22 11 = 0x11223344")],
                [green("opcodes"), plain("nop=90 int3=CC ret=C3")],
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
