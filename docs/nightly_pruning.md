# Pruning old nightly builds from S3

Nightly builds are uploaded to `s3://compiler-explorer/opt/` as `<family>-<YYYYMMDD>.tar.<ext>`
and nothing else ever removes them. `ce_install prune-nightlies` keeps the newest few builds
of each nightly family and deletes the rest.

```bash
bin/ce_install prune-nightlies              # dry run: prints what it would remove and keep
bin/ce_install prune-nightlies --delete     # actually delete
bin/ce_install prune-nightlies --keep 10    # keep 10 build dates instead of the default 5
```

It runs daily from `crontab.admin`, replacing `remove_old_compilers.sh` (see #2289 for why
the shell version missed 1.3 TiB of builds).

## What decides that a build may be deleted

The installation YAML, not a name pattern. Every `type: nightly` installable knows the S3
prefix its dated artifacts use - the same `compiler_name` / `s3_name` fields it fetches with,
read through `Installable.dated_s3_prefix` - so a nightly is covered by the cull the moment it
is added, whatever it is called. The previous shell script matched only
`-(main|trunk|master)-` and so never touched `rust-miri-nightly`, `micropython-preview` or
`6502-c++-trunk` (the `+` fell outside its character class).

`nightlytarballs` installables are not involved: they fetch from upstream release URLs, so
they have no artifacts of ours to prune.

## Keeping is by rank, not age

The newest `--keep` *build dates* per family survive; everything older goes. Two artifacts
sharing a date count as one build and are kept or removed together. Ranking by date rather
than by age is why this is a command and not an S3 lifecycle rule: a compiler that stops
being built keeps its last builds instead of eventually losing all of them.

## Families the YAML does not claim

Dated families that no installable claims are printed and **never deleted**, split into those
still being built (something is uploading builds nothing installs - a blind spot to fix) and
dormant ones (relics of compilers long gone, e.g. `clang-cppx`, last built in 2017). Deciding
between "wire it back into the YAML" and "delete the lot" needs a human; the command's job is
to make sure the choice is visible rather than silent. Remove them by hand with
`aws s3 rm` once you have decided.
