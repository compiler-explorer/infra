---
name: admin-exec
description: This skill should be used when running anything on the CE admin node from a workstation, such as installing a merged compiler or library ("install it on admin", "install the compiler on admin"), running a `ce` subcommand there, restarting or checking the conan proxy, or reaching the conan node (which only accepts SSH from admin). Covers the quoting-safe base64 wrapper for `bin/ce admin exec`, sudo installs, and the conan hop.
version: 0.1.0
---

# Running commands on the admin node

Work from the infra repo root; `bin/ce` is a relative path. If local `bin/ce`
prints "python environment is out of date", run `make ce` locally. The message
comes from the local wrapper, not from admin.

## The wrapper

`bin/ce admin exec` sends its arguments over SSH. Admin's login shell is fish,
and `exec_remote` joins arguments with POSIX quoting. Anything with spaces,
quotes, `&&` or `;` arrives mangled, and a plain `admin exec -- bash -lc '...'`
fails with status 127. Base64-encode the command so it survives both layers:

```bash
CMD=$(printf '%s' 'cd /home/ubuntu/infra && <command>' | base64 -w0)
bin/ce admin exec -- bash -c "echo $CMD | base64 -d | bash"
```

A single bare-word command needs no wrapper; give `ce` its full path:

```bash
bin/ce admin exec /home/ubuntu/infra/bin/ce conan restart
```

The admin checkout is `/home/ubuntu/infra`.

## Installing a merged compiler or library

Pull first so the merged YAML is there, check that the installable resolves,
then install with **sudo**. Install the exact version, never a whole group:

```bash
CMD=$(printf '%s' "cd /home/ubuntu/infra && git pull -q --ff-only && git log --oneline -1 && ./bin/ce_install list '<name>'" | base64 -w0)
bin/ce admin exec -- bash -c "echo $CMD | base64 -d | bash"

CMD=$(printf '%s' "cd /home/ubuntu/infra && sudo ./bin/ce_install install '<name> <version>' 2>&1 | tail -8 && ./bin/ce_install list '<name>' --installed-only" | base64 -w0)
bin/ce admin exec -- bash -c "echo $CMD | base64 -d | bash"
```

Installs on admin go through CEFS: the result is a symlink
`/opt/compiler-explorer/<dir> -> /cefs/<hash>/...`. Afterwards, run the
installable's check command (e.g. `<exe> --version`) to confirm it.

If `git log` doesn't show the merge commit, check the pull before installing.
Otherwise ce_install quietly reports nothing matching the filter.

A `PermissionError` under `/tmp/ce-cefs-temp` means sudo was missing. CEFS's
working directories are root-owned. Don't route around it with
`--cefs-temp-dir` or `--staging-dir`; rerun with sudo.

## Conan proxy

After `ce conan restart`, wait about 10 seconds before making requests; it returns
502 while starting up.

The conan node doesn't accept SSH from a workstation (it times out); hop through
admin:

```bash
CMD=$(printf '%s' 'cd /home/ubuntu/infra && ./bin/ce conan exec -- df -h' | base64 -w0)
bin/ce admin exec -- bash -c "echo $CMD | base64 -d | bash"
```

## Gotchas
- Status 127 from a remote command almost always means quoting broke; use the
  base64 wrapper.
- Errors are in the traceback's *preceding* output. Don't `tail` so tightly
  that you only see `RuntimeError: Remote command execution failed with status N`.
- Run one logical task per call, with its steps chained by `&&` inside the
  payload.
