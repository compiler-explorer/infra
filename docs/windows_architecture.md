# Windows architecture

Covers the environments winprod, winstaging and wintest.

## How to make a new build

1. Let the normal workflow deploy a linux build and note the gh-number
2. Manually run [CE Windows Build](https://github.com/compiler-explorer/compiler-explorer/actions/workflows/deploy-win.yml) with the same gh-number
3. Run `ce --env winstaging builds set_current gh-number`
4. Run `ce --env winstaging environment start`

There is no compiler discovery for the Windows environment.

## User code execution restrictions

User code Executions runs through cewrapper. It creates an appcontainer environment and adds the user's temporary directory as the only directory where things can be executed within. The appcontainer also enables firewall rules and registry restrictions.

The runtime .dll's (libstdc++, libpthread, etc) are sometimes needed for execution. We're currently unable to give access to the dll's because it seems impossible to setup the right ACL's on the network share. Instead, they are copied to the user's temp directory before execution.

(It might be possible to set ACL's when using FSx and an AD instead of using Samba for the network share)

## Compiler and tools restrictions

Compilers are not running through appcontainer yet, but it does use cewrapper for execution, and it's running using the ce user which has certain restrictions that are setup in `init/start.ps1`.

## Bootstrapping

### AMI

The AMI is confused by running `packer/InstallPwsh.ps1` and `packer/InstallTools.ps1`. Despite installing powershell 7, these scripts will execute using the default powershell installed with Windows. At the end of installing the tools, a service is configured to execute the `packer/Startup.ps1` on startup of the instance.

### Startup

Using a service that runs under the user `NETWORK-SERVICE`

1. Pulls the latest infra
2. Runs `init/start.ps1`
   - Sets up Grafana Agent
   - Downloads the CE built code
   - Sets up firewall to disallow most things except for allowed hosts, nginx and node
   - Creates a new user `ce` with a randomly generated password
   - Adds new service to run `init/run.ps1` (manually once right now) under the `ce` user
3. Runs `init/run.ps1`
   - Mounts Z: to have access to the compilers
   - Runs CE
