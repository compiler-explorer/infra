#!/usr/bin/env python3
"""Compile a simple program on each given CE compiler id and print a pass/fail table.

Usage:
    compile_matrix.py --base http://localhost:10240 LANG:ID [LANG:ID ...]

Each positional arg is `lang:compilerid`, e.g. `c++:aocc520`, `fortran:aoccflang500`.
A simple per-language program is used (override with --source 'lang=...').
Exits non-zero if any compile fails (code != 0 or no asm produced).
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request

DEFAULT_SOURCES = {
    "c++": "int square(int num) { return num * num; }\n",
    "c": "int square(int num) { return num * num; }\n",
    "fortran": ("integer function square(n)\n  integer, intent(in) :: n\n  square = n * n\nend function\n"),
    "_default": "int square(int num) { return num * num; }\n",
}


def compile_one(base: str, lang: str, cid: str, src: str, args: str, timeout: int) -> tuple[object, int, str]:
    body = {
        "source": src,
        "compiler": cid,
        "lang": lang,
        "options": {
            "userArguments": args,
            "filters": {
                "labels": True,
                "directives": True,
                "comments": True,
                "intel": True,
                "demangle": True,
                "execute": False,
            },
            "compilerOptions": {},
            "tools": [],
        },
    }
    req = urllib.request.Request(
        f"{base}/api/compiler/{cid}/compile",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        res = json.load(resp)
    code = res.get("code")
    asm = res.get("asm") or []
    asm_lines = sum(1 for a in asm if (a.get("text") or "").strip())
    err = " ".join(x.get("text", "") for x in (res.get("stderr") or []))[:200]
    return code, asm_lines, err


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://localhost:10240")
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--args", default="-O2", help="userArguments passed to every compile (default: -O2)")
    parser.add_argument(
        "--source",
        action="append",
        default=[],
        metavar="LANG=SRC",
        help="Override the inline source for a language",
    )
    parser.add_argument(
        "--source-file",
        action="append",
        default=[],
        metavar="LANG=PATH",
        help="Read the source for a language from a file (e.g. an interpreted DSL example)",
    )
    parser.add_argument("cases", nargs="+", metavar="LANG:ID")
    args = parser.parse_args()

    sources = dict(DEFAULT_SOURCES)
    for override in args.source:
        lang, _, src = override.partition("=")
        sources[lang] = src
    for override in args.source_file:
        lang, _, path = override.partition("=")
        with open(path, encoding="utf-8") as handle:
            sources[lang] = handle.read()

    print(f"{'lang':8} {'compiler':16} {'code':4} {'asmLines':8} note")
    print("-" * 72)
    all_ok = True
    for case in args.cases:
        lang, _, cid = case.partition(":")
        src = sources.get(lang, sources["_default"])
        try:
            code, asm_lines, err = compile_one(args.base, lang, cid, src, args.args, args.timeout)
            ok = code == 0 and asm_lines > 0
            all_ok = all_ok and ok
            note = "OK" if ok else f"FAIL: {err}"
            print(f"{lang:8} {cid:16} {str(code):4} {asm_lines:<8} {note}")
        except Exception as exc:  # noqa: BLE001 - report any failure per-row
            all_ok = False
            print(f"{lang:8} {cid:16} {'ERR':4} {'-':8} {exc}")
    print("-" * 72)
    print("ALL PASS" if all_ok else "SOME FAILED")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
