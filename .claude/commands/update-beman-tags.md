Discover newly-released git tags on `bemanproject/*` repos and propose
infra + compiler-explorer changes to expose them.

The infra repo (this one) hosts `bin/yaml/libraries.yaml`. The
compiler-explorer repo lives in a sibling directory (look around
`../compiler-explorer` or `../compiler-explorer-*`); its config file is
`etc/config/c++.amazon.properties`. If you can't find a sibling clone,
ask the user to point at the right path before continuing.

## What to do

1. **Enumerate beman libraries declared in this repo.** Each one has an
   entry under the `nightly:` group inside `bin/yaml/libraries.yaml`
   with a `repo: bemanproject/<name>` line. Build the list of repos
   from there — do not hard-code it.
2. **Fetch tags via `gh api`** for each repo, e.g.
   `gh api repos/bemanproject/<name>/tags --jq '.[].name'`. Skip repos
   with no tags. Exclude pre-release / rc / alpha / beta tags unless
   the user asks otherwise.
3. **Compare against what's already configured.** For each library look
   at the existing top-level (non-nightly) entry in
   `bin/yaml/libraries.yaml`. Build a set of `(target_prefix +
   target_name)` strings already present and compute the diff against
   the GitHub tag list.
4. **If there are no new tags, stop and report that to the user.** Do
   not open empty PRs.
5. **Add the new tagged versions** to `bin/yaml/libraries.yaml`,
   following the conventions already in place:
   - Header-only libs: `build_type: none`, `check_file: README.md`,
     `type: github`.
   - The one built lib (`beman_iterator_interface`) keeps its
     `cmake` / `staticliblink` / `package_install` settings.
   - When all of a repo's tags are `v`-prefixed, set
     `target_prefix: v` and list bare versions.
   - For tags without the `v`, use a per-target
     `target_prefix: ''` override on a `name: <ver>` dict.
   - Do **not** put new tagged entries under the `nightly:` group, and
     do **not** use `method: nightlyclone` — the default `archive`
     method is what we want.
6. **Validate locally** before committing:
   ```bash
   bin/ce_install list 'libraries/c++/beman_*'
   bin/ce_install --dry-run --dest ~/opt/compiler-explorer install \
       'libraries/c++/beman_<lib> <ver>'
   ```
   For at least the new tags, run a real install into
   `~/opt/compiler-explorer` and confirm the install path
   (`libs/beman_<lib>/<target_prefix><ver>/`) contains the expected
   `include/`.
7. **Update the compiler-explorer config.** Open
   `etc/config/c++.amazon.properties` in the sibling clone and extend
   each affected `libs.beman_<lib>.versions=...` list. Use the same
   compact version key style the file already uses (e.g. `0.1.0` →
   `010`, `2.1.1` → `211`). The `path` entry must match the install
   directory created by `ce_install`, including the `v` prefix when
   present.
8. **Run `npm run test:props`** in the compiler-explorer repo to make
   sure the property file is still valid.
9. **Open two PRs**, one in each repo, on a fresh branch. Match the
   style of the existing PRs (e.g.
   https://github.com/compiler-explorer/infra/pull/2111 and
   https://github.com/compiler-explorer/compiler-explorer/pull/8683):
   - Infra branch first, then reference its PR number from the
     compiler-explorer PR description.
   - Don't bypass pre-commit hooks. Terraform-related hook failures on
     a workstation without `terraform` installed are environmental, not
     a real failure — but everything else must pass.
10. **Report back** the full list of tags added per library and the two
    PR URLs so the user can review.

## Things to skip

- Repos with zero tags (e.g. execution, map, net, span, task at time of
  writing) — they remain nightly-only.
- Pre-release / rc / alpha / beta tags.
- Re-running the discovery for repos that already have the latest tag
  configured.

## Notes

- Pre-commit will run tests and lint. You'll need `make pre-commit`
  green on the infra side; on the compiler-explorer side `make
  pre-commit` (or at minimum `npm run test:props`) must pass.
- Don't add anything to `c++.amazonwin.properties` unless the user
  asks — the Windows build path for these libs hasn't been wired up.
- Don't touch the existing `nightly:` `beman_*` entries; their `main`
  trunk build is independent of tagged releases.
