---
name: launch-env
description: This skill should be used when starting up or redeploying a blue-green environment (staging, beta) that has been shut down, e.g. "launch staging", "start beta again", "bring staging up with the same release", "redeploy staging". Covers running the deploy on admin, picking the version, clearing stray instances on the inactive colour, and shutting the environment down again.
version: 0.1.0
---

# Launching a blue-green environment

staging, beta and prod are blue-green. `ce environment start` does nothing for them;
use `blue-green deploy`. Don't launch prod with this skill. A prod deploy needs the
interactive notification prompt and the user's explicit go-ahead.

## Run it on admin, not locally

Deploys run on the admin node. Use the admin-exec skill's base64 wrapper:

```bash
CMD=$(printf '%s' 'cd /home/ubuntu/infra && ./bin/ce --env staging blue-green status 2>&1 | tail -30' | base64 -w0)
bin/ce admin exec -- bash -c "echo $CMD | base64 -d | bash"
```

You can read state locally (`bin/ce --env staging builds current`), but never run
`deploy`, `cleanup`, `switch` or `shutdown` from the workstation.

## Steps

1. Find the version. "Same release as before" means the build that's already set:
   `bin/ce --env staging builds current` gives e.g. `version=gh-19618`. Otherwise
   use the build the user names.
2. Check `blue-green status` on admin. Look at the *inactive* colour, because the
   deploy scales that one up.
3. If the inactive ASG already has instances, the deploy refuses with
   `--skip-confirmation` ("existing instances found"). These are leftovers from an
   earlier attempt and don't count as a valid deploy. Run
   `./bin/ce --env staging blue-green cleanup --skip-confirmation`, then deploy
   straight away. Don't wait for the old instance to terminate.
4. Deploy, in a single call with a 10-minute timeout:

   ```bash
   CMD=$(printf '%s' 'cd /home/ubuntu/infra && ./bin/ce --env staging blue-green deploy gh-NNNNN --skip-confirmation 2>&1 | tail -60' | base64 -w0)
   bin/ce admin exec -- bash -c "echo $CMD | base64 -d | bash"
   ```

   If the active ASG is at 0, capacity defaults to `max(1, env.min_instances)`.
   The command sets the version, scales up the inactive colour, waits for HTTP
   health and compiler registration, switches traffic, updates compiler routing
   and clears the ce-router cache. Expect about 2-3 minutes.
5. Check the output ends with `Deployment successful!`. Report the new active
   colour, the compiler count, and that the old colour has nothing to roll back to
   if it was at 0.

## Shutting it down again

`./bin/ce --env staging blue-green shutdown --skip-confirmation` scales the active
ASG to 0. Use `cleanup` on its own when only the inactive colour needs clearing.

## Gotchas

- Auto mode may block deploy/cleanup as a shared-resource change. If it does, show
  the user the exact command and let them approve or run it with `! ...`.
- Verify over HTTP at `https://godbolt.org/staging/api/version`, never
  `staging.godbolt.org`. That hostname serves prod.
