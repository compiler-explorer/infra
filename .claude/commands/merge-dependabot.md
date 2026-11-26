# Merge Dependabot PRs

Merge the open dependabot PRs in compiler-explorer/infra. Only dependabot PRs: if a PR's author is not
`app/dependabot`, leave it alone.

Treat every dependabot PR as a security update that needs to land. Most of this repo needs nothing beyond a merge:
the CLI and scripts are picked up by `git pull` wherever they run. The exception is the lambdas, which only change
in AWS when their package is rebuilt, uploaded and applied with terraform. Everything runs end to end, including
that redeploy, but a PR that fails a gate is skipped (not merged) and reported, never forced through. Stop and ask
me only when the terraform plan contains more than the lambda update, or when a terraform command fails.

## 1. Find the PRs

```bash
gh pr list --author app/dependabot --state open \
    --json number,title,headRefName,mergeStateStatus,files,url
```

If there are none, say so and stop.

Classify each PR by its `files`:

- **python lambda**: anything under `lambda/` (usually `lambda/uv.lock`)
- **events lambda**: anything under `events-lambda/`
- **github-actions**: only `.github/workflows/*` (the monthly grouped PR)
- **root python**: `pyproject.toml`/`uv.lock` at the repo root (the `bin/` CLI and tooling)
- **analytics**: `analytics/`, a manually run script on the admin node, never deployed

A PR touching more than one area goes through the gates of every area it touches.

## 2. Rebase via dependabot

For each PR whose `mergeStateStatus` is `BEHIND`, `DIRTY` or otherwise not up to date with main, comment
`@dependabot rebase` (`gh pr comment <N> --body '@dependabot rebase'`) and wait for dependabot to push the
rebased branch. Never rebase or push to a dependabot branch yourself.

After merging one PR, the others may fall behind. Ask for a rebase again before merging the next one.

## 3. Gates (all must pass per PR)

### CI green

`gh pr checks <N> --watch`. Every required check must pass. A failing check means skip the PR and report it.
CI already builds both lambda zips (`make lambda-package events-lambda-package` in `tests.yaml`), which catches
resolution failures but not runtime incompatibilities (see "Lambda runtime check" below).

### Changelog review

The PR body holds the release notes, changelog and commits dependabot pulled from upstream. Read them, and for
anything that's cut off, follow the links to the upstream release pages.

The most important checks, in order:

1. **Breaking changes**: anything labelled "breaking", "BREAKING CHANGE", "removed", "dropped support" or
   "no longer" anywhere in the range being skipped over, not only in the target release.
2. **Major version bumps**: any change in the major number (or the minor number for `0.x` packages). This
   includes transitive dependencies that move a major version in the lockfile diff.
3. **Runtime requirements** (lambda PRs): a raised minimum Python or Node version, a new or changed native
   extension, a newly required system library, or new wheels built against a newer glibc/manylinux tag.

Then use judgement about what we actually use from the package: grep for its imports and usage (`bin/lib/`,
`lambda/`, `events-lambda/`, `analytics/`, workflow files) and decide whether a change affects us and whether I
should know about it. Say nothing about changes that don't affect us.

For github-actions, check each bumped action's release notes for changed inputs/outputs or a new required
runner/Node version, and grep the workflows for the inputs we pass. Self-hosted runners (admin node, builders)
may lag behind GitHub-hosted ones, so a new minimum runner version matters.

### Python and Node version requirements

Check every bumped package, transitive ones included, for a change in the interpreter it supports: a raised
`requires-python` / `Requires-Python` (look in the package's `pyproject.toml` or the PyPI page for the new version,
and in `uv.lock`, where `requires-python` and per-wheel `cp3xx` tags show it), a dropped Python minor in the
classifiers or changelog, or a raised `engines.node`. Even a minor-version move counts: a package that now needs
3.13 can't run on the `python3.12` lambda runtime or on whatever Python the admin node and builders use, and a
patch release of a dependency is enough to trigger it.

Compare against everything that pins our versions: `.python-version` and `requires-python` in `pyproject.toml`
(root and `lambda/`), `target-version` in the ruff config, `runtime` in `terraform/lambda*.tf`, and `engines` plus
the Node version pinned in `.github/workflows/tests.yaml` for `events-lambda/`.

If a bump needs a newer Python or Node than any of those, don't merge it and don't try to work around it (pinning
an older version, editing `.python-version`, changing the lambda runtime). Bring it to me in the report for
discussion: which package, which version first required it, and everything that would have to move with it.

### Verdict

A breaking or major change that affects code we use means: don't merge. Report it with what would have to change.
A breaking or major change that doesn't touch anything we use can be merged, but say in the report that you
checked and why it's safe.

### Local test run

Use a worktree so main stays clean:

```bash
git fetch origin <headRefName>
git worktree add ../infra-dependabot-<N> origin/<headRefName>
```

Run the checks for whatever the PR touches:

- **python lambda**: `uv run pytest lambda -v` from the worktree root, then `make lambda-package`
- **events lambda**: in `events-lambda/`, `npm ci`, `npm run lint`, `npm test`, then `make events-lambda-package`
  from the worktree root
- **root python**: `make test` and `make static-checks`, then `uv run bin/ce --help` to check the CLI still imports
- **analytics**: in `analytics/`, `npm ci`, then `node -e "require('<package>')"` to check the bumped package
  loads. Don't run `compilestats.js`: it talks to Google Analytics and S3. Grep it and `lib/` for the APIs we call
  instead
- **github-actions**: CI on the PR is the test, so nothing extra locally

Remove the worktree afterwards with `git worktree remove --force ../infra-dependabot-<N>`. `--force` is needed
because `.venv`/`node_modules`/`.dist` are untracked.

### Lambda runtime check

Any PR touching `lambda/` or `events-lambda/`. Passing tests here proves very little: tests run on this machine's
OS, CPU and Python/Node, and the package is built here too. AWS runs it somewhere else.

First establish the target from terraform, not from memory:

```bash
grep -n 'runtime\|architectures' terraform/lambda*.tf
```

Python lambdas share `lambda-package.zip` and have no `architectures` line, so they run x86_64. The events lambdas
are `arm64`. Then look up the runtime on AWS's documentation, the only place the OS is listed:
https://docs.aws.amazon.com/lambda/latest/dg/lambda-runtimes.html. Note the OS (e.g. Amazon Linux 2023), and from
there its glibc version and which runtime-provided packages exist (for Node, which AWS SDK v3 version is bundled;
for Python, which boto3/botocore). Also check the deprecation dates: if the runtime is near end of support, say so
in the report.

Then check what we'd ship against that:

- **Python wheels**: `scripts/build_lambda_deterministic.py` installs with `uv pip install` for the host, with no
  `--python-platform`. Any dependency with a compiled extension (charset-normalizer ships mypyc wheels, for one)
  gets a wheel picked for this machine's glibc, not the lambda's. List what landed in the package and its tags:

  ```bash
  unzip -l .dist/lambda-package.zip | grep -E '\.so'
  find lambda/.build_site_packages -name WHEEL -path '*dist-info*' 2>/dev/null
  ```

  `.dist-info` is stripped from the zip, so if `.build_site_packages` doesn't keep it, check which wheel uv would
  choose with `uv pip install --dry-run --python-platform x86_64-manylinux_2_34 ...` versus the host. Fail the
  gate if any `.so` needs a newer glibc than the lambda OS provides (`objdump -T <file>.so | grep -o 'GLIBC_[0-9.]*' | sort -uV | tail -1`),
  or a CPython ABI other than the runtime's (a `cpython-313` `.so` won't load on `python3.12`).
- **Node modules**: `scripts/build_nodejs_lambda_deterministic.py` runs `npm install --production` on this x86_64
  machine. Any package with a native addon (`*.node`, `binding.gyp`, a `prebuilds/` dir, or an install script)
  would ship an x86_64 binary to an arm64 lambda. Check the built zip with
  `unzip -l .dist/events-lambda-package.zip | grep -E '\.node$|binding\.gyp|prebuilds'`; any hit fails the gate.
  Also check `engines` of the bumped packages against the runtime's Node major.
- **Runtime-provided packages**: `@aws-sdk/*` is bundled into our zip, so the version in our lockfile is what runs,
  but check the bump doesn't need a newer Node than the runtime. For Python, don't add or rely on boto3 being
  pinned in our package unless it is; the runtime's own boto3 is used otherwise.

If the change can't be verified this way and touches anything with native code, say so and don't merge it without
asking me.

## 4. Merge

For each PR that passed every gate, one at a time:

```bash
gh pr merge <N> --squash
```

Never use `--admin` and never bypass branch protection. Request a fresh `@dependabot rebase` for the next PR if
it fell behind (see step 2).

If nothing merged touched `lambda/` or `events-lambda/`, stop here and report. There's nothing to deploy.

## 5. Report

Report before redeploying, then carry on without waiting:

- merged PRs (number, package, from → to, whether it was a security fix)
- skipped PRs and why
- relevant changelog notes (breaking or major changes and how they affect us)
- any Python/Node version requirement change, held back for discussion
- local test results, and for lambda PRs the runtime check: the runtime, arch and OS from terraform/AWS docs, and
  why the shipped package is compatible
- which lambdas need a redeploy: every python lambda (`cloudwatch_to_discord`, `alert_on_elb_instance`, `stats`,
  `status`, `get_deployed_exe_version`, `get_remote_execution_archs`; re-check with
  `grep -l lambda_zip terraform/*.tf`) for a `lambda/` change, the three `events-*` lambdas for an `events-lambda/`
  change

## 6. Redeploy lambdas

From an up-to-date main checkout (`git pull` first, so the package is built from the merged lockfile), upload the
rebuilt zips and save a plan:

```bash
make upload-lambda upload-events-lambda
terraform -chdir=terraform plan -out=dependabot.tfplan
```

Uploading doesn't change the running lambdas, since they're pinned to an S3 object version until terraform moves
them. `make terraform-apply` would do both steps, but its `terraform apply` waits for an interactive `yes`, and
applying a saved plan guarantees that what gets applied is what you reviewed.

Check the plan: it should only update the `aws_lambda_function` resources for the affected lambdas
(`s3_object_version` and `source_code_hash`). If it shows anything else, someone has unapplied terraform changes
on main: stop and tell me, don't apply them along with this. If the plan is clean:

```bash
terraform -chdir=terraform apply dependabot.tfplan
rm terraform/dependabot.tfplan
```

If the plan or apply fails (state lock, credentials, a provider error), stop and tell me with the error. Don't
force-unlock state or retry with different flags.

### Verify

- **events lambdas**: they back the websocket used for live events. Check
  `aws logs tail /aws/lambda/events-sendmessage --since 10m` (and `events-onconnect`) for errors after the apply.
  An `ImportModuleError`/`Runtime.ImportModuleError` or `ERR_MODULE_NOT_FOUND` means the package doesn't run.
- **python lambdas**: `status` and `get_deployed_exe_version` serve HTTP, so look up their routes in terraform
  (`grep -rn 'aws_lambda_function.status\|get_deployed_exe_version' terraform/`) and hit them. For the others,
  tail their log groups (`/aws/lambda/<name>`) after the next invocation, or the next few minutes for `stats`,
  which is fed continuously. `Runtime.ImportModuleError`, `invalid ELF header`, `GLIBC_x.yy not found` or
  `undefined symbol` mean a native wheel didn't match the runtime.

If a lambda fails, tell me straight away with the error. Rolling back is a revert of the merge followed by the same
plan/apply, so don't open a revert PR without asking me.
