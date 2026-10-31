---
name: deploy-windows-build
description: This skill should be used before deploying a Compiler Explorer build or a new AMI to a Windows environment (winstaging, winprod, wintest), for example "deploy to winstaging", "put gh-NNNNN on winstaging", "deploy the new windows ami", or "promote winstaging to winprod". It gives the required order (Windows zip, then discovery, then blue-green deploy) and the checks between steps. Skipping a step, above all discovery, is the mistake this exists to prevent.
version: 0.1.0
---

# Deploying a Windows build

Read `docs/windows_architecture.md` first. The order below is mandatory. Never
start a `blue-green deploy` on a Windows environment until steps 1-3 are done for
that exact build number.

1. Pick the build (Linux gh-number)
2. Build the Windows zip for it
3. Run discovery for it and upload to the target environment
4. Blue-green deploy, on admin
5. Verify
6. Prod is a separate step with its own go-ahead

Steps 1-4 are about the CE build. A new AMI only changes the launch template
(`winstaging_image_id` etc. in `terraform/lc.tf`, applied by hand). The next
blue-green deploy picks it up, and the deploy still needs steps 1-3 first.

## 1. Pick the build

The build number is the `gh-NNNNN` tag on compiler-explorer, made by the normal
Linux pipeline. If a specific fix has to be in it, check that before going on:

```bash
gh api "repos/compiler-explorer/compiler-explorer/tags?per_page=10" --jq '.[] | [.name,.commit.sha[0:9]] | @tsv'
gh api repos/compiler-explorer/compiler-explorer/compare/<fix-sha>...<build-sha> --jq .status   # "identical" or "ahead" = included
```

Don't reuse the build the environment or winprod already runs without checking.
It may predate the change being tested.

## 2. Windows zip

Windows zips exist only for builds someone ran `deploy-win.yml` for. Check:

```bash
aws s3 ls s3://compiler-explorer/dist/gh/main/NNNNN.zip
```

If it's missing, start the build. `ce workflows deploy-win` currently fails with
HTTP 422 (it sends a `branch` input the workflow doesn't have), so use `gh`:

```bash
gh workflow run deploy-win.yml --repo compiler-explorer/compiler-explorer -f buildnumber=gh-NNNNN
gh run list --repo compiler-explorer/compiler-explorer --workflow deploy-win.yml --limit 1
gh run watch <run-id> --repo compiler-explorer/compiler-explorer --exit-status
```

It takes a few minutes. Before going on, confirm the zip exists and that
`dist/gh/main/NNNNN.txt` holds the expected commit.

## 3. Discovery

Check whether it already exists:

```bash
aws s3 ls s3://compiler-explorer/dist/discovery/winstaging/gh-NNNNN.json
```

Normally run the workflow:

```bash
bin/ce workflows run-win-discovery gh-NNNNN --environment winstaging --wait
```

It runs on admin's GitHub runner, which takes one job at a time. If
`gh run list --repo compiler-explorer/infra --limit 5` shows something long
holding it (e.g. "Scheduled Linux Library Builds"), run the same steps directly
on admin with `run-win-discovery-on-admin.sh` from this skill's directory:

```bash
.claude/skills/deploy-windows-build/run-win-discovery-on-admin.sh gh-NNNNN winstaging
```

Pitfalls:
- The runner loads its build at boot. If it's already running (e.g. terraform
  just replaced it after an AMI bump), stop it and wait for `stopped` before
  `start`. `win-runner stop` returns without waiting, and `start` skips starting
  if the state is `stopping`, so `stop; start` back to back runs discovery
  against a dying instance.
- If the runner is up when nobody started it, a discovery may be in flight.
  Check before stopping it.
- One discovery serves winstaging and winprod. `ce win-runner promote gh-NNNNN`
  copies the winstaging file to winprod.

## 4. Deploy (on admin)

Run blue-green deploys on admin, not with local `bin/ce`:

```bash
B64=$(printf '%s' '/home/ubuntu/infra/bin/ce --env winstaging blue-green status 2>&1 | tail -20' | base64 -w0)
bin/ce admin exec -- bash -c "echo $B64 | base64 -d | bash"
B64=$(printf '%s' '/home/ubuntu/infra/bin/ce --env winstaging blue-green deploy gh-NNNNN --skip-confirmation 2>&1 | tail -30' | base64 -w0)
bin/ce admin exec -- bash -c "echo $B64 | base64 -d | bash"
```

If the inactive colour has stray instances, run `blue-green cleanup` first. A
deploy started by mistake can be stopped before traffic switches. Kill the
`blue-green deploy` process on admin by PID (stopping the local ssh doesn't kill
it), then run `blue-green cleanup --skip-confirmation`. The active colour keeps
serving.

## 5. Verify

- `curl -s https://godbolt.org/winstaging/api/version` shows the build's commit.
- The instance runs the expected AMI: `aws ec2 describe-instances --filters Name=tag:aws:autoscaling:groupName,Values=winstaging-<colour>`.
- Compile and execute through the API (`https://godbolt.org/winstaging/api/compiler/<id>/compile`)
  for the compilers the change touches. Instances are reachable as
  `Administrator@<private-ip>`, from admin only.

## 6. winprod

Never as part of a winstaging request. Once winstaging checks out and the user
gives the go-ahead: `ce win-runner promote gh-NNNNN`, then
`ce --env winprod blue-green deploy gh-NNNNN` on admin. An AMI bump for winprod
is a separate `terraform/lc.tf` change.
