# Windows architecture

Covers the environments winprod, winstaging and wintest.

## How to make a new build

1. Let the normal workflow deploy a linux build and note the gh-number
2. Manually run [CE Windows Build](https://github.com/compiler-explorer/compiler-explorer/actions/workflows/deploy-win.yml) with the same gh-number
3. Run `ce workflows run-win-discovery gh-number` (optional, see below)
4. Run `ce --env winstaging builds set_current gh-number`
5. Run `ce --env winstaging environment start`

## Compiler discovery

Discovery runs on `CEWinRunner`, a stopped-by-default instance built from the same image as the
fleet. `ce workflows run-win-discovery <buildnumber>` starts it, runs `init/do-discovery.ps1`
over ssh, checks the result and uploads it to `dist/discovery/<environment>/gh-<n>.json`. The
`ce win-runner` commands do each step individually.

`init/start.ps1` downloads that file for its own environment at boot and `init/run.ps1` passes
it as `--prediscovered`, so instances skip running every compiler themselves. It is optional:
without it Compiler Explorer discovers as it always did, just more slowly.

One run serves both winprod and winstaging. They share a compiler share, and their properties
differ only in `httpRoot`, `motdUrl` and `sentryEnvironment`, so discovery runs as `--env
winprod` and is uploaded to whichever environment is asked for.

Windows instances are reachable over ssh as `Administrator` (see Bootstrapping), which is what
the runner commands use.

## Updating CMake and Ninja

CMake and Ninja are not `ce_install` installables on Windows. They are baked into the images as
`C:\BuildTools\CMake` and `C:\BuildTools\Ninja`, one copy per image:

* `packer/InstallTools.ps1` for the node image. This is what the site runs: CE's
  `compiler-explorer.amazonwin.properties` names them outright as
  `cmake=C:/BuildTools/CMake/bin/cmake.exe` and `ninjaPath=C:/BuildTools/Ninja`.
* `packer/InstallBuilderTools.ps1` for the library builder image. `init/start-builder.ps1` puts it on
  PATH and `library_builder.py` invokes bare `cmake`, so this one decides what library builds get.

The two are separate knobs and have drifted apart before. Keep them on the same version unless you
have a reason not to, and remember the Linux builder is a third: it takes whichever cmake carries the
`symlink: cmake` marker in `bin/yaml/tools.yaml`, via `init/start-builder.sh`.

Both scripts bump the same way: edit the download URL and the `Rename-Item` source directory in
`InstallBuildTools`. Getting the result deployed differs.

For the node image:

1. `make packer-win`
2. Put the new AMI id in `winstaging_image_id` in `terraform/lc.tf`, apply, and restart winstaging
3. Once it's proven, point `winprod_image_id` at it and restart winprod

`ec2.tf` derives the win-runner image from `winstaging_image_id`, so that follows along.

The builder image is built in the ce-ci repo, not here. Its `packer/windows-provisioner.ps1` fetches
`InstallBuilderTools.ps1` from this repo's main branch by raw URL, so a change only takes effect once
it is merged and someone runs `./build-image-win-builder.sh` over there. Nothing needs an AMI id
updating afterwards: `templates/runner-configs/windows-x64-win-builder.yaml` selects the image by the
`github-runner-win-builder-*` name filter, and `win-lib-build.yaml` runs on whichever runner the
ce-ci scaler hands it.

`init/start-builder.ps1` behaves differently again. `win-lib-build.yaml` downloads it from main at job
time, so changes to it land on the next build with no image rebuild at all.

The compiler share used to carry `cmake-v*` and `ninja-v*` installables as well. Nothing ever read
them -- both images use their own `C:\BuildTools` copy -- so they were dropped from
`bin/yaml/windows.yaml`. Don't add them back without a consumer.

## User code execution restrictions

User code Executions runs through cewrapper. It creates an appcontainer environment and adds the user's temporary directory as the only directory where things can be executed within. The appcontainer also enables firewall rules and registry restrictions.

The runtime .dll's (libstdc++, libpthread, etc) are sometimes needed for execution. We're currently unable to give access to the dll's because it seems impossible to setup the right ACL's on the network share. Instead, they are copied to the user's temp directory before execution.

(It might be possible to set ACL's when using FSx and an AD instead of using Samba for the network share)

## Compiler and tools restrictions

Compilers are not running through appcontainer yet, but it does use cewrapper for execution, and it's running using the ce user which has certain restrictions that are setup in `init/start.ps1`.

## Bootstrapping

### AMI

The AMI consists of running `packer/InstallPwsh.ps1` and `packer/InstallTools.ps1`. Despite installing powershell 7, these scripts will execute using the default powershell installed with Windows. At the end of installing the tools, a service is configured to execute the `packer/Startup.ps1` on startup of the instance.

### Startup

Using a service that runs under the user `NETWORK-SERVICE`

1. Resets the firewall, then pulls the latest infra. The reset matters: the rules `init/start.ps1`
   installs survive a reboot and block DNS, so without it github is unreachable on every boot
   after the first and none of the steps below ever run again.
2. Runs `init/start.ps1`
   - Installs the authorized keys from `s3://compiler-explorer/authorized_keys` and starts sshd,
     first, so an instance that fails later is still reachable
   - Sets up Grafana Agent
   - Downloads the CE built code, and its discovery json if one exists
   - Sets up firewall to disallow most things except for allowed hosts, nginx and node
   - Creates a new user `ce` with a randomly generated password
   - Adds new service to run `init/run.ps1` (manually once right now) under the `ce` user
3. Runs `init/run.ps1`
   - Mounts Z: to have access to the compilers
   - Runs CE

Anything that needs the internet has to happen before the firewall is configured, and hosts
outside its allowlist are unreachable afterwards -- there is no updating infra on a running
instance, only rebooting it.
