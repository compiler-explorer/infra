Discover newly-released git tags on `bemanproject/*` repos and propose
infra + compiler-explorer changes to expose them.

The infra repo (this one) hosts `bin/yaml/libraries.yaml`. The
compiler-explorer repo lives in a sibling directory (look around
`../compiler-explorer` or `../compiler-explorer-*`); its config file is
`etc/config/c++.amazon.properties`. If you can't find a sibling clone,
ask the user to point at the right path before continuing.

## Where things live

Both groups now live under shared `beman:` parents that declare common
settings (`build_type`, `check_file`, `target_prefix`, `type`, and a
templated `repo: bemanproject/{{ context[-1] | replace('beman_', '', 1) }}`):

- **Tagged versions** — `libraries.c++.beman.beman_<lib>` (no `if:`,
  default archive method).
- **Trunk** — `libraries.c++.nightly.beman.beman_<lib>` (inherits
  `if: nightly` and `method: nightlyclone` from the surrounding
  `nightly:` group).

Most leaves only declare `targets:`. Genuine overrides today:
`beman_iterator_interface` (cmake / staticliblink / package_install)
and `beman_scope` (`target_prefix: ''` because its only tag is
`0.0.1`). Per-target `target_prefix: ''` is also used for individual
non-`v`-prefixed tags within otherwise-`v`-prefixed libraries
(e.g. `beman_any_view`'s `1.0.0`, several `beman_exemplar` versions).

## What to do

1. **Enumerate beman libraries.** The authoritative list is the keys
   under `libraries.c++.nightly.beman` in `bin/yaml/libraries.yaml`
   (it's a superset, including repos that have no tags yet). Don't
   hard-code names.
2. **Fetch tags via `gh api`** for each repo, e.g.
   `gh api repos/bemanproject/<name>/tags --jq '.[].name'`. Skip repos
   with no tags. Exclude pre-release / rc / alpha / beta tags unless
   the user asks otherwise.
3. **Compare against what's already configured.** Look at the keys and
   targets under `libraries.c++.beman` to see which `(target_prefix +
   target_name)` strings are already present, and compute the diff
   against the GitHub tag list.
4. **If there are no new tags, stop and report that to the user.** Do
   not open empty PRs.
5. **Add the new tagged versions** under `libraries.c++.beman`. Match
   the existing style:
   - If the lib doesn't have an entry yet, add a child whose only key
     is `targets:`. Common settings are inherited from the parent.
   - When all of a lib's tags are `v`-prefixed, list bare versions
     under `targets:` and rely on the parent's `target_prefix: v`.
   - For tags missing the `v`, add a per-target dict with
     `target_prefix: ''`:
     ```yaml
     - name: 1.0.0
       target_prefix: ''
     ```
   - When **none** of a lib's tags are `v`-prefixed, override at the
     entry level with `target_prefix: ''` (see `beman_scope`).
   - `beman_iterator_interface` is the only built lib; preserve its
     `cmake` / `lib_type: static` / `staticliblink` / `package_install`
     overrides if you're adding a new tag for it.
   - Don't introduce `method: nightlyclone` here; the default `archive`
     method is correct for tagged versions.
6. **Validate locally** before committing:
   ```bash
   bin/ce_install list 'libraries/c++/beman/**'
   bin/ce_install --dry-run --dest ~/opt/compiler-explorer install \
       'libraries/c++/beman/beman_<lib> <ver>'
   ```
   For at least the new tags, run a real install into
   `~/opt/compiler-explorer` and confirm the install path
   (`libs/beman_<lib>/<target_prefix><ver>/`) contains the expected
   `include/`. Note the install dir uses `target_prefix + target_name`,
   so a tag `v0.1.0` installs at `libs/beman_<lib>/v0.1.0/` and a
   bare `0.0.1` tag installs at `libs/beman_<lib>/0.0.1/`.
7. **Update the compiler-explorer config.** Open
   `etc/config/c++.amazon.properties` in the sibling clone and extend
   each affected `libs.beman_<lib>.versions=...` list. Use the same
   compact version key style the file already uses (e.g. `0.1.0` →
   `010`, `2.1.1` → `211`). The `path` entry must match the install
   directory created by `ce_install`, including the `v` prefix when
   present (so `0.1.0` from a `v0.1.0` tag becomes
   `.../beman_<lib>/v0.1.0/include`, while `0.0.1` from a bare
   `0.0.1` tag becomes `.../beman_<lib>/0.0.1/include`).
8. **Run `npm run test:props`** in the compiler-explorer repo to make
   sure the property file is still valid.
9. **Open two PRs**, one in each repo, on a fresh branch. Match the
   style of the existing PRs (see compiler-explorer/infra#2111 and
   compiler-explorer/compiler-explorer#8683):
   - Infra branch first, then reference its PR number from the
     compiler-explorer PR description.
   - Don't bypass pre-commit hooks. Terraform-related hook failures on
     a workstation without `terraform` installed are environmental, not
     a real failure — but everything else must pass.
10. **Report back** the full list of tags added per library and the two
    PR URLs so the user can review.

## Things to skip

- Repos with zero tags (e.g. `beman_execution`, `beman_map`,
  `beman_net`, `beman_span`, `beman_task` at time of writing). Their
  `libraries.c++.nightly.beman.<name>` trunk entries stay; nothing
  needs to be added under `libraries.c++.beman`.
- Pre-release / rc / alpha / beta tags.
- Re-running the discovery for repos that already have the latest tag
  configured.

## Notes

- Pre-commit will run tests and lint. `make pre-commit` (infra) and
  `npm run test:props` (compiler-explorer) must be clean.
- Don't touch `c++.amazonwin.properties` unless the user asks — the
  Windows path for these libs hasn't been wired up.
- Don't touch the `libraries.c++.nightly.beman.*` entries; their
  `main` trunk install is independent of tagged releases.
