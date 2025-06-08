# Release new site version

This doc covers the process of releasing a new build version to the live site.

First of all, note that each commit generates a build artifact with an id of `gh-xxxx`.
It's important to first wait until the CI has generated such artifact, and then find the id of your target commit.
(It will be tagged to your target commit automatically)

## Ensure your build has been successfully uploaded by CI

Login into the admin node with `ce admin login`, and once there remember to connect to the tmux session,
with `tmux at` (`Ctrl+B, D` by default to later detach instead of closing the connection).

Now run `ce --env staging builds list` and make sure that your target `gh-xxxx` build is present.

_If this is not the case, make sure that there were no errors in the CI, or ask around for help._

## Run compiler discovery of your target build

Run a "Compiler Discovery" workflow in https://github.com/compiler-explorer/infra/actions/workflows/compiler-discovery.yml

You need to fill 3 inputs:
 - **Environment**: This is usually `staging`, but can be run for `beta` and `prod` too
 - **Branch**: The branch that your target commit belongs to. Usually `main`
 - **Build number**: The `gh-xxxx` id you identified

Alternatively, you can use the GitHub CLI to run this workflow:

`gh workflow run -R compiler-explorer/infra 'Compiler discovery' -f buildnumber=gh-xxxx`

It usually takes less than 5 min. for the discovery to run.

## Set current version in staging

Once the discovery has finished, you can proceed to set the build as the current release version in staging.
(The idea is to first test in staging as a last check before bouncing the version in prod)

Once there, `ce --env staging builds set_current gh-xxxx` will set the current build version
for staging to your identified build id.

Note that `--env staging` comes before any command, and its default value is always `staging`,
but this document uses it explicitly to be more clear as to what is running for which environment.

After passing the sanity checks (it will ask you to confirm what branch this comes from and in what env you're running the command in),
the build has been marked as current.  Note that these sanity checks are present in most commands,
and we're always on the lookout for more places to put them, so if you find anything not secured by these checks,
please do let us know.

_If this fails due to some hash missmatch errors, you need to bump the hack version number in `webpack.config.esm.js`,
and restart this process with the new commit as the target._

## Bringing staging up

Now staging needs to be brought up. This is done with `ce --env staging environment start`.
The message should be that the number of instances has been increased from 0 to 1 (Or more!)

If this is not the case, it means that staging was already up and you'll need to instead refresh those instances.
This is accomplished by running `ce --env staging environment refresh`.
This can take a bit until all the new nodes are healthy.

Once this is done, the new version is running in https://godbolt.org/staging
(You can confirm it by going to Other > Version Tree, which points to the release commit in GitHub)

## Bringing staging down

Unless staging is currently in use for something else, you should now always remember to bring staging down.

This is unsurprisingly accomplished by running `ce --env staging environment stop`.

## Mark discovery run as safe for production

Instead of now rerunning the first step of compiler discovery for your commit but now for the prod environment,
you can instead run `ce runner safeforprod staging gh-xxxx`, and it will create a compiler discovery result for prod.

## Set current version in prod

Now that you've tested that everything works correctly,
running `ce --env prod builds set_current gh-xxxx` will mark your build as current for the prod environment.

_If this fails complaining that prod is currently bounce locked, it means that someone has blocked prod from updating.
The usual reason is that a conference is currently running and we don't want to have any big changes at this moment.
There are instructions in the error message on how to bypass this if necessary, but ask around to check first._

## Deploy to production (Blue-Green)

Production now uses blue-green deployment for zero-downtime updates. Instead of refreshing instances,
you'll deploy to the inactive color and then switch traffic:

### Check current status
```bash
ce --env prod blue-green status
```

This shows which color (blue or green) is currently active and serving traffic.

### Deploy to inactive color
```bash
ce --env prod blue-green deploy
```

This will:
1. Deploy new instances to the inactive color
2. Wait for all health checks to pass
3. Automatically switch traffic to the new version
4. Keep the old version as standby for quick rollback

The deployment typically takes 10-15 minutes depending on the number of instances.

### Alternative: Manual deployment steps

If you prefer more control, you can use individual commands:

```bash
# Deploy without automatic switch
ce --env prod blue-green deploy --skip-switch

# Manually switch when ready
ce --env prod blue-green switch {blue|green}

# If issues arise, rollback instantly
ce --env prod blue-green rollback
```

### Cleanup old version

After confirming the new version is stable, clean up the old instances:

```bash
ce --env prod blue-green cleanup
```

This scales down the inactive ASG to save costs.

## Done

Congratulations, you've deployed the live site to a new version using blue-green deployment!

The benefits of this approach:
- Zero downtime during deployment
- No mixed versions serving traffic
- Instant rollback capability if issues are detected
- Previous version remains available as backup

We now usually go to all the PR/issues that this new build implements and comment that they are now live in each of them.

Please submit a PR to this document if you find that something could be better explained/is just plain wrong.
