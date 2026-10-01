#!/usr/bin/env python3
"""Compile (and optionally run) a simple program on each given CE compiler id and print a pass/fail table.

Usage:
    compile_matrix.py --base http://localhost:10240 LANG:ID [LANG:ID ...]
    compile_matrix.py --execute --base http://localhost:10240 LANG:ID [LANG:ID ...]

Each positional arg is `lang:compilerid`, e.g. `c++:aocc520`, `fortran:aoccflang500`.
A simple per-language program is used (override with --source 'lang=...' or --source-file 'lang=path').

Default mode checks the disassembly path: pass = compile code 0 and non-empty asm.
--execute checks the execution path instead: pass = didExecute and execResult.code 0.
These are separate code paths -- a compiler can disassemble fine yet fail to execute
(e.g. a misresolved interpreter), so run both for languages that set supportsExecute.
Exits non-zero if any case fails.
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


def compile_one(base: str, lang: str, cid: str, src: str, args: str, execute: bool, timeout: int) -> dict:
    options: dict[str, object] = {
        "userArguments": args,
        "filters": {
            "labels": True,
            "directives": True,
            "comments": True,
            "intel": True,
            "demangle": True,
            "execute": execute,
        },
        "compilerOptions": {},
        "tools": [],
    }
    if execute:
        options["executeParameters"] = {"args": [], "stdin": ""}
    body = {"source": src, "compiler": cid, "lang": lang, "options": options}
    req = urllib.request.Request(
        f"{base}/api/compiler/{cid}/compile",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        res = json.load(resp)
    asm = res.get("asm") or []
    exec_res = res.get("execResult") or {}
    exec_stdout = " ".join(x.get("text", "") for x in (exec_res.get("stdout") or [])).strip()
    # The build/setup stderr (e.g. a failed interpreter spawn) surfaces at the top level.
    setup_err = " ".join(x.get("text", "") for x in (res.get("stderr") or [])).strip()
    return {
        "code": res.get("code"),
        "asm_lines": sum(1 for a in asm if (a.get("text") or "").strip()),
        "did_execute": exec_res.get("didExecute"),
        "exec_code": exec_res.get("code"),
        "stdout": exec_stdout,
        "setup_err": setup_err,
    }


def run_disassembly(cases: list[tuple[str, str]], sources: dict, opts: argparse.Namespace) -> bool:
    print(f"{'lang':8} {'compiler':16} {'code':4} {'asmLines':8} note")
    print("-" * 72)
    all_ok = True
    for lang, cid in cases:
        src = sources.get(lang, sources["_default"])
        try:
            r = compile_one(opts.base, lang, cid, src, opts.args, False, opts.timeout)
            ok = r["code"] == 0 and r["asm_lines"] > 0
            note = "OK" if ok else f"FAIL: {r['setup_err'][:200]}"
            print(f"{lang:8} {cid:16} {str(r['code']):4} {r['asm_lines']:<8} {note}")
        except Exception as exc:  # noqa: BLE001 - report any failure per-row
            ok = False
            print(f"{lang:8} {cid:16} {'ERR':4} {'-':8} {exc}")
        all_ok = all_ok and ok
    return all_ok


def run_execution(cases: list[tuple[str, str]], sources: dict, opts: argparse.Namespace) -> bool:
    print(f"{'lang':8} {'compiler':16} {'didExec':7} {'exit':4} note")
    print("-" * 72)
    all_ok = True
    for lang, cid in cases:
        src = sources.get(lang, sources["_default"])
        try:
            r = compile_one(opts.base, lang, cid, src, opts.args, True, opts.timeout)
            ok = r["did_execute"] is True and r["exec_code"] == 0
            note = (f"stdout={r['stdout'][:60]!r}" if ok else f"FAIL: {r['setup_err'][:200]}").strip()
            print(f"{lang:8} {cid:16} {str(r['did_execute']):7} {str(r['exec_code']):4} {note}")
        except Exception as exc:  # noqa: BLE001 - report any failure per-row
            ok = False
            print(f"{lang:8} {cid:16} {'ERR':7} {'-':4} {exc}")
        all_ok = all_ok and ok
    return all_ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://localhost:10240")
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--args", default="-O2", help="userArguments passed to every compile (default: -O2)")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Check the execution path (didExecute + execResult.code) instead of disassembly",
    )
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
    opts = parser.parse_args()

    sources = dict(DEFAULT_SOURCES)
    for override in opts.source:
        lang, _, src = override.partition("=")
        sources[lang] = src
    for override in opts.source_file:
        lang, _, path = override.partition("=")
        with open(path, encoding="utf-8") as handle:
            sources[lang] = handle.read()

    cases = [(case.partition(":")[0], case.partition(":")[2]) for case in opts.cases]
    all_ok = run_execution(cases, sources, opts) if opts.execute else run_disassembly(cases, sources, opts)
    print("-" * 72)
    print("ALL PASS" if all_ok else "SOME FAILED")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
