# Release new site version

This doc covers the process of releasing a new build version to the live site.

Each commit to `main` generates a build artifact with an id of `gh-xxxx`.
Wait until CI has generated the artifact, then find the id for your target commit.
(It will be tagged to your target commit automatically.)

## Ensure your build has been successfully uploaded by CI

Login to the admin node with `ce admin login`, and connect to the tmux session
with `tmux at` (`Ctrl+B, D` to detach later instead of closing the connection).

Run `ce --env staging builds list` and make sure your target `gh-xxxx` build is present.

_If it's not there, check for errors in CI, or ask around for help._

## Run compiler discovery

Compiler discovery fires up CE on a dedicated runner instance, interrogates all the compilers,
and saves the results to speed up subsequent startups. This is only needed for Linux x86 deploys
(staging, prod, beta). Windows and GPU environments don't use discovery.

Run the "Compiler Discovery" workflow: https://github.com/compiler-explorer/infra/actions/workflows/compiler-discovery.yml

Inputs:
 - **Environment**: Usually `staging`
 - **Branch**: Usually `main`
 - **Build number**: The `gh-xxxx` id you identified

Or via the GitHub CLI:

```bash
gh workflow run -R compiler-explorer/infra 'Compiler discovery' -f buildnumber=gh-xxxx
```

This takes about 5 minutes. Behind the scenes it starts a runner instance, sets the build,
runs discovery, uploads the results, and shuts the runner down.

## Deploy to staging

All environments use blue-green deployment. Deploy your build to staging:

```bash
ce --env staging blue-green deploy gh-xxxx
```

This spins up instances on the inactive color, waits for health checks and compiler registration,
then switches traffic. Once it's up, test at https://godbolt.org/staging
(confirm the version via Other > Version Tree).

_If the deploy fails due to a hash mismatch, bump the hack version number in `webpack.config.esm.js`
and restart this process with the new commit._

_If any command fails complaining about a bounce lock, someone has blocked that environment from
updating (usually during a conference). There are instructions in the error message on how to
bypass this, but check with the team first._

## Test staging

Do your testing. Once you're happy, clean up staging:

```bash
ce --env staging blue-green cleanup
```

## Deploy to production

```bash
ce --env prod blue-green deploy gh-xxxx
```

If compiler discovery hasn't been run for prod, the tooling will offer to copy the discovery
results from staging automatically.

The deploy will:
1. Spin up new instances on the inactive color
2. Wait for health checks and compiler registration
3. Switch traffic to the new version
4. Keep the old version on standby for rollback

This typically takes 10-15 minutes.

### Manual control

If you want more control over the process:

```bash
# Deploy without automatic traffic switch
ce --env prod blue-green deploy gh-xxxx --skip-switch

# Manually switch when ready
ce --env prod blue-green switch {blue|green}

# If something goes wrong, rollback instantly
ce --env prod blue-green rollback
```

### Cleanup

After confirming the new version is stable, scale down the old instances:

```bash
ce --env prod blue-green cleanup
```

## Other environments

### Windows

Windows needs a separate build from the same source.

1. Wait for the Linux build `gh-xxxx` to complete
2. Manually run the [CE Windows Build](https://github.com/compiler-explorer/compiler-explorer/actions/workflows/deploy-win.yml) workflow with the same `gh-xxxx`
3. There is no compiler discovery for Windows
4. Deploy to staging and prod as usual:

```bash
ce --env winstaging blue-green deploy gh-xxxx
# test, then:
ce --env winprod blue-green deploy gh-xxxx
```

### AArch64

AArch64 uses the same Linux build as x86 (no separate build needed). Deploy via:

```bash
ce --env aarch64staging blue-green deploy gh-xxxx
# test, then:
ce --env aarch64prod blue-green deploy gh-xxxx
```

### GPU

GPU has no staging environment. Deploy directly to prod, then run compiler discovery
afterwards (the reverse of the normal order):

```bash
ce --env gpu blue-green deploy gh-xxxx
# then trigger compiler discovery for gpu
```

## Useful commands

```bash
ce --env <env> blue-green status     # Check current state
ce --env <env> blue-green deploy     # Deploy (with version list)
ce --env <env> blue-green rollback   # Instant rollback
ce --env <env> blue-green cleanup    # Scale down inactive
ce --env <env> blue-green shutdown   # Shut down environment
ce --env <env> builds list           # List available builds
```

## "Now live" notifications

When deploying to prod, the tooling will ask whether to send "now live" notifications.
If you opt in, it compares the old and new commit ranges, finds all merged PRs and their
linked issues, and posts a "This is now live" comment and adds a `live` label to each.

Note that this is based purely on which commits are in the new build, not which environments
they affect. If you merged a GPU-only change and then deployed only prod, the notification
will still fire for that GPU change. Keep this in mind and use your judgement.

See `lib/notify.py` and the `--notify`/`--no-notify`/`--dry-run-notify` flags on
`blue-green deploy` for details.

## Done

Please submit a PR to this document if you find something that could be better explained or is wrong.
