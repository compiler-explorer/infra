---
name: verify-compilers-locally
description: This skill should be used when the user wants to verify that newly-added compilers actually install and compile in a real Compiler Explorer instance before/after merging a PR. Triggers include "test the compilers locally", "verify this compiler PR", "do they all compile", "run a local CE and check compiler X", or adopting an infra install-config + CE properties pair (like AOCC, ICX, a new GCC/Clang group). Covers the full loop: ce_install the compilers (plus toolchain deps), launch CE locally with extracted local.properties, drive the compile API across every new compiler id, report a pass/fail table, then tear down.
version: 0.1.0
---

# Verify compilers locally

End-to-end check that a set of new compilers installs and compiles a simple
program inside a real CE instance. This is the loop behind "does this compiler
PR actually work", exercising the real production config (exe paths,
`--gcc-toolchain`, group settings, `compilerType`) without any AWS bootstrap.

Two repos are involved:
- **infra** (this repo): `bin/yaml/*.yaml` install config, run via `bin/ce_install`.
- **compiler-explorer**: `etc/config/<lang>.amazon.properties` compiler definitions.

Find both checkouts before starting. The CE checkout is usually a sibling
(`../compiler-explorer`); a PR under test is often a `git worktree`.

## Procedure

### 1. Identify the targets
From the CE properties PR, list the new compiler **ids** per language and the
group(s) they belong to. From the infra PR, get the matching `ce_install`
filter (e.g. `compilers/c++/aocc`). Confirm with:
```bash
uv run bin/ce_install list 'compilers/c++/aocc'
```

### 2. Install the compilers (+ toolchain deps)
Default dest is `/opt/compiler-explorer` (must be writable). Install the group:
```bash
uv run bin/ce_install install 'compilers/c++/aocc'
```
**Resolve `--gcc-toolchain` deps.** Inspect the properties `options=` for the
group: clang-based compilers usually pass
`--gcc-toolchain=/opt/compiler-explorer/gcc-X.Y.Z`. That GCC must exist locally
or `clang++` can't find libstdc++. Install it too:
```bash
uv run bin/ce_install install 'compilers/c++/x86/gcc 14.2.0'
```
Verify the expected binaries exist (`bin/clang`, `bin/clang++`, `bin/flang`,
etc.) under each install dir before continuing.

### 3. Extract local.properties (do NOT use `--env amazon`)
`--env amazon` triggers AWS/instance bootstrap you don't want locally. Instead
layer the relevant blocks as `local` properties (loaded last, highest
precedence, gitignored). For each language, pull just the target group + its
compiler entries out of the amazon file:
```bash
cd <ce-checkout>
{ echo "compilers=&aocc"; echo "defaultCompiler=aocc520";
  grep -E '^group\.aocc\.|^compiler\.aocc[0-9]' etc/config/c++.amazon.properties; } \
  > etc/config/c++.local.properties
```
Repeat per language with the right group name (`aocc` / `caocc` / `aocc_flang`)
and id prefix. These files are gitignored — they are throwaway.

### 4. Launch CE locally
Needs `node_modules` (run `npm ci` in the checkout/worktree if absent). Then:
```bash
nohup npm run dev -- --port 10240 > /tmp/ce_dev.log 2>&1 &
```
Wait for `Listening on http://localhost:10240/`. The log will say
`Failed to create N out of M compilers` — that's expected (other languages'
compilers aren't installed locally). Confirm your targets loaded:
```bash
curl -s "http://localhost:10240/api/compilers/c++?fields=id,name" \
  -H "Accept: application/json" | python3 -c "import sys,json;[print(c['id']) for c in json.load(sys.stdin) if 'aocc' in c['id']]"
```

### 5. Compile-test every id
Use the helper to POST a simple program to each compiler via the compile API
and print a pass/fail table (exit code 0 + non-empty asm = OK):
```bash
python3 .claude/skills/verify-compilers-locally/compile_matrix.py \
  --base http://localhost:10240 \
  c++:aocc320 c++:aocc400 ... c:caocc320 ... fortran:aoccflang320 ...
```
Spot-check one real asm output to confirm it's genuine codegen, not a masked
error.

### 6. Teardown
```bash
pkill -f "app.ts --port 10240"
rm -f <ce-checkout>/etc/config/*.local.properties   # so the next `npm run dev` isn't AOCC-only
```
Leave the `/opt/compiler-explorer` installs in place unless asked to remove
them (they're slow to re-fetch). Report what was left installed.

## Gotchas (hard-won)
- **Never `--env amazon` locally** — it does AWS-side things. Use `local.properties`.
- **Remove `local.properties` afterwards** or the user's next `npm run dev` shows only your test compilers.
- **`--gcc-toolchain` GCC must be installed** or clang C/C++ fails to find the stdlib. Fortran/flang doesn't need it.
- Compile API: `POST /api/compiler/<id>/compile`, JSON body, `Accept: application/json`; check `code==0` and a non-empty `asm` array.
- **`code==0` + non-empty asm is necessary, not sufficient.** A wrapper can exit 0 and emit a *placeholder* (e.g. "// No PTX was generated") that still counts as asm lines — a false pass. Always eyeball the actual output for at least one compiler per distinct line-count bucket; differing asm-line counts across versions usually means some produce real output and others a fallback.
- Interpreted DSLs (cutedsl, triton): the source comes from `examples/<lang>/default.py`, not the built-in C snippet. Pass it with `--source-file <lang>=<path>` and usually `--args ""` (per-compiler flags like `--arch sm_90a` already come from config). Real output may live in the `devices` map (MLIR/SASS/PTX views), not just `asm`.
- The CE properties repo uses **squash merges only**.
