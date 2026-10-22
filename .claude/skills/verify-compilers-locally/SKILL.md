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
filter (e.g. `compilers/c++/aocc`). List what it matches and pick the exact
installables the PR adds:
```bash
uv run bin/ce_install list 'compilers/c++/aocc'
```
Read the infra diff for renamed targets too. Changing an existing target (e.g.
`"0.15"` to `"0.15.0"`) makes ce_install treat it as a new version and install
the same release again under a new directory; the PR should keep the old name.

For `s3tarballs` (and other prebuilt) installables, confirm every tarball exists
before installing. A "Build Required" comment from github-actions on the infra
PR lists the `bespoke-build.yaml` commands; until those have run, the install
can't be tested:
```bash
curl -sI https://s3.amazonaws.com/compiler-explorer/opt/pythran-0.19.0.tar.xz | head -1
```
A failing bespoke build may be the builder image, not the version: read the
log before blaming the compiler.

### 2. Install the compilers (+ toolchain deps)
Default dest is `/opt/compiler-explorer` (must be writable). Install only the
exact versions selected from the `list` output, never a whole group: a filter
like `compilers/c++/x86/gcc`, `clang` or `rust` matches hundreds of versions and
will spend hours downloading and fill the disk.
```bash
uv run bin/ce_install install 'compilers/c++/aocc 5.0.0'
```
If the install fails with `Permission denied: '/efs/cefs-images/...'`, the
machine's config enables CEFS; add `--force-traditional` (before `install`) to
extract into `/opt/compiler-explorer` instead.

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
compiler entries out of the amazon file.

The user may already have their own `*.local.properties` in the checkout. Move
them aside first so they neither leak into the test nor get deleted at
teardown. If `mkdir` fails, a previous run's backup was never restored:
restore it (step 6) before continuing, never overwrite it.
```bash
cd <ce-checkout>
mkdir /tmp/ce_local_backup && \
  find etc/config -maxdepth 1 -name '*.local.properties' -exec mv -t /tmp/ce_local_backup {} +
ls /tmp/ce_local_backup   # note what was backed up, to report at the end
```
Then write the test files:
```bash
{ echo "compilers=&aocc"; echo "defaultCompiler=aocc520";
  grep -E '^group\.aocc\.|^compiler\.aocc[0-9]' etc/config/c++.amazon.properties; } \
  > etc/config/c++.local.properties
```
Repeat per language with the right group name (`aocc` / `caocc` / `aocc_flang`)
and id prefix. These files are gitignored — they are throwaway.

### 4. Launch CE locally
Needs `node_modules` (run `npm ci` in the checkout/worktree if absent). Then:
```bash
setsid bash -c 'echo $$ > /tmp/ce_dev.pid; exec npm run dev -- --port 10240' > /tmp/ce_dev.log 2>&1 < /dev/null &
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

For languages that set `supportsExecute` (interpreters, `interpreted=true`),
also run the **execution** path -- it's a separate code path from disassembly,
so a compiler can disassemble fine yet fail to run (e.g. a misresolved
interpreter). Add `--execute`; it checks `didExecute` + `execResult.code`:
```bash
python3 .claude/skills/verify-compilers-locally/compile_matrix.py --execute \
  --base http://localhost:10240 lua:lua515 lua:lua550 ...
```

For groups that set `supportsBinary=true`, also run with `--binary`. Some
compilers only invoke the backend toolchain in binary mode (pythran emits C++
by default and builds a module only for binary), so the default run alone
misses toolchain problems:
```bash
python3 .claude/skills/verify-compilers-locally/compile_matrix.py --binary --args "" \
  --source-file python=/path/to/pythran_test.py --base http://localhost:10240 python:pythran0190 ...
```

### 6. Teardown
```bash
kill -- -"$(cat /tmp/ce_dev.pid)" && rm -f /tmp/ce_dev.pid   # setsid made it a group leader; this also kills npm's children
cd <ce-checkout>
rm -f etc/config/*.local.properties   # the test files, so the next `npm run dev` isn't AOCC-only
find /tmp/ce_local_backup -maxdepth 1 -name '*.local.properties' -exec mv -t etc/config {} + && \
  rmdir /tmp/ce_local_backup
```
Check `etc/config` holds exactly the files listed from the backup in step 3.
Leave the `/opt/compiler-explorer` installs in place unless asked to remove
them (they're slow to re-fetch). Report what was left installed.

## Gotchas (hard-won)
- **Never `--env amazon` locally** — it does AWS-side things. Use `local.properties`.
- **Back up the user's own `local.properties` before writing yours, and restore them afterwards.** Removing only the test files is not enough if theirs were overwritten; leaving yours means their next `npm run dev` shows only your test compilers.
- **Never install a whole compiler group** (gcc, clang, rust, ...). `list` first and install exact versions.
- **`--gcc-toolchain` GCC must be installed** or clang C/C++ fails to find the stdlib. Fortran/flang doesn't need it.
- Compile API: `POST /api/compiler/<id>/compile`, JSON body, `Accept: application/json`; check `code==0` and a non-empty `asm` array (or `devices[].asm` for GPU compilers).
- **Disassembly passing does NOT mean execution works.** They're separate paths: the asm/listing comes from the compiler, execution runs a (possibly different) binary. A real bug shipped where every Lua version disassembled correctly but all executed with the wrong interpreter — the disassembly matrix was all-green. For `supportsExecute` languages, run `compile_matrix.py --execute` too and confirm `didExecute` + `execResult.code==0` (and the stdout looks right).
- **`code==0` + non-empty asm is necessary, not sufficient.** A wrapper can exit 0 and emit a *placeholder* (e.g. "// No PTX was generated") that still counts as asm lines — a false pass. Always eyeball the actual output for at least one compiler per distinct line-count bucket; differing asm-line counts across versions usually means some produce real output and others a fallback.
- Interpreted DSLs (cutedsl, triton): the source comes from `examples/<lang>/default.py`, not the built-in C snippet. Pass it with `--source-file <lang>=<path>` and usually `--args ""` (per-compiler flags like `--arch sm_90a` already come from config). Real output may live in the `devices` map (MLIR/SASS/PTX views), not just `asm`.
- **A system compiler can mask a missing toolchain.** Compiler classes that append a toolchain `bin` to the *end* of PATH (e.g. pythran's `cpp_compiler_root`) still find `/usr/bin/g++` locally, so a wrong or missing root passes here and fails in production. Pointing the setting at a bogus path and getting a pass proves nothing; say the check was inconclusive.
- Pythran sources need a `#pythran export name(type)` line, or there is nothing to compile; pass one with `--source-file python=<path>` and `--args ""`.
- The CE properties repo uses **squash merges only**.
