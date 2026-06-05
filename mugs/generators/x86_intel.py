"""x86-64 (Intel syntax) architecture cheat-sheet generator."""

from core.cheatsheet import Block, CheatSheet, DiagramBar, RegDiagram, green, plain

from .cheatsheet_base import CheatSheetGenerator


class X86IntelCheatSheetGenerator(CheatSheetGenerator):
    """x86-64 Intel-syntax cheat sheet."""

    def get_cheatsheet(self) -> CheatSheet:
        # Show the architectural sub-register nesting (RAX > EAX > AX > AH|AL)
        # rather than a flat list; calling-convention roles live on the ABI mug.
        registers = RegDiagram(
            heading="Registers",
            bars=[
                DiagramBar(bits="64", fraction=1.0, segments=["RAX"]),
                DiagramBar(bits="32", fraction=0.5, segments=["EAX"]),
                DiagramBar(bits="16", fraction=0.25, segments=["AX"]),
                DiagramBar(bits="8", fraction=0.25, segments=["AH", "AL"]),
            ],
            notes=[
                "+ RBX RCX RDX RSI RDI RBP RSP R8-R15",
                "32-bit write zero-extends; 8/16 don't",
            ],
        )

        syntax = Block(
            heading="Syntax",
            rows=[
                [green("op dst, src"), plain("dest first")],
                [green("[b+i*s+d]"), plain("base+index*scale+disp")],
                [green("dword ptr"), plain("byte/word/dword/qword")],
                [green("mov rax,42"), plain("bare immediate")],
                [green("[rip+sym]"), plain("RIP-relative")],
            ],
        )

        instructions = Block(
            heading="Instructions",
            rows=[
                [green("mov"), plain("copy r / m / imm")],
                [green("movzx/movsx"), plain("widen: zero / sign")],
                [green("lea"), plain("address calc / arith")],
                [green("add/sub"), plain("add / subtract")],
                [green("imul"), plain("signed multiply")],
                [green("idiv"), plain("signed div (RDX:RAX)")],
                [green("cdq/cqo"), plain("sign-extend for idiv")],
                [green("and/or/xor"), plain("bitwise  (xor r,r=0)")],
                [green("shl/shr/sar"), plain("shift L / R / arith-R")],
                [green("cmp / test"), plain("flags: a-b / a&b")],
                [green("setcc"), plain("set byte on cond")],
                [green("cmovcc"), plain("conditional move")],
                [green("jmp / jcc"), plain("jump / conditional")],
                [green("call / ret"), plain("call / return")],
                [green("push / pop"), plain("stack push / pop")],
                [green("endbr64"), plain("CET pad (fn entry)")],
            ],
        )

        flags = Block(
            heading="Flags & Jcc (after cmp a,b)",
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
                [green("xor eax,eax"), plain("zero rax (breaks deps)")],
                [green("lea"), plain("multiply + add, no flags")],
                [green("endian"), plain("44 33 22 11 = 0x11223344")],
                [green("opcodes"), plain("nop=90 int3=CC ret=C3")],
            ],
        )

        return CheatSheet(
            title="x86-64  Intel syntax",
            columns=[
                [instructions, idioms],
                [registers, syntax, flags],
            ],
            footer="Compiler Explorer",
        )


if __name__ == "__main__":
    generator = X86IntelCheatSheetGenerator()
    command = generator.get_click_command()
    command()
