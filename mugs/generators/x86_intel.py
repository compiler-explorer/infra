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
                "+ RBX RCX RDX RSI RDI RBP RSP",
                "R8-R15: R8D R8W R8B",
                "EAX write zero-extends; AX/AL don't",
            ],
        )

        syntax = Block(
            heading="Syntax",
            rows=[
                [green("op dst, src"), plain("dest first")],
                [green("[b+i*s+d]"), plain("base+index*scale+disp")],
                [green("dword ptr"), plain("byte/word/dword/qword")],
                [green("x[rip]"), plain("RIP-relative (gcc)")],
                [green("OFFSET FLAT:x"), plain("address of x (gcc)")],
            ],
        )

        instructions = Block(
            heading="Instructions",
            rows=[
                [green("mov"), plain("copy r / m / imm")],
                [green("movzx/movsx"), plain("widen 0/sign, movsxd")],
                [green("lea"), plain("address calc / arith")],
                [green("imul"), plain("multiply (u or s)")],
                [green("div/idiv"), plain("u/s divide RDX:RAX")],
                [green("cdq/cqo"), plain("sign-extend for idiv")],
                [green("and/or/xor"), plain("bitwise")],
                [green("shl/shr/sar"), plain("shift L / R / arith-R")],
                [green("cmp / test"), plain("flags: a-b / a&b")],
                [green("setcc/cmovcc"), plain("set byte / mov if cc")],
                [green("endbr64"), plain("CET pad (fn entry)")],
                [green("_ss _sd"), plain("scalar float / double")],
                [green("_ps _pd"), plain("packed float / double")],
                [green("vaddps"), plain("AVX: 3-op, ymm/zmm")],
            ],
            notes=["+ add sub jmp jcc call ret push pop"],
        )

        flags = Block(
            heading="Flags & cc (after cmp a,b)",
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
                [green("xor eax,eax"), plain("zero rax (breaks deps)")],
                [green("test r,r"), plain("r==0? (then je/jne)")],
                [green("imul+shr"), plain("divide by constant")],
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
