# MSVCE

These are the scripts which should be used to build the MSVCE data directory and
docker image.

## Requirements

* PowerShell v6 or later - you can download this via https://github.com/PowerShell/PowerShell
* Docker for Windows

## Instructions

There are two parts of the MSVCE pipeline: the docker image, which contains the
node.js software, the compiler explorer server, and the windows SDK; and the
file share, which contains the toolsets (i.e., the Visual C++ compiler and
libraries), the libraries (from vcpkg), and some configuration for the server.

The configuration involved for the image and data directory lives in
`msvce-config.json`. The schema exists as `msvce-config-schema.json`.

Before doing anything else, you must import the involved module:

```pwsh
PS > Import-Module .\Msvce.psm1
```

### Building the Docker Image

In order to build the docker image, in case you modify either the server
version, the Windows SDK version, the node version, or the docker image, one
should run the following command:

```pwsh
PS > Build-MsvceDockerImage -DockerTag [yyyymmdd]
```

(for example, on 2019-09-05, you'd write)

```pwsh
PS > Build-MsvceDockerImage -DockerTag 20190905
```

Any additional docker images built on the same day should be tagged
`yyyymmdd-2`, `yyyymmdd-3`, etc.

### Building the Data Directory

In order to build the data directory, there are 4 concerns you must first figure
out.

* Are you adding new compilers?
* Are you adding new libraries?
  * Are you updating vcpkg itself?
* Are you building from scratch, or do you have an existing data directory?
* Are you building it locally, or for the MSVCE server?

Remember that all the information you should be interested in exists in the
`msvce-config.json` file.

If you're interested in speeding up the building of the data directory, you
should look into the `Get-Help` for `Build-MsvceDataDirectory` -- however, it
shouldn't be that terrible if you just run it in the default configuration.

Some useful parameters:
* If you're not adding new compilers; you may pass the `-SkipVerifyToolsets` flag
* If you aren't updating vcpkg, you can pass the `-SkipVcpkgBootstrap`
* If you aren't adding new libraries, you can pass `-SkipVcpkgLibraries`. The existing
toolsets won't be touched.

For the default case: you're adding new compilers, and updating vcpkg, and
you're building it for the MSVCE server, one should do the following:

```pwsh
PS > # First, import the module
PS > Import-Module .\Msvce.psm1
PS > # Now we can create the data directory
PS > Build-MsvceDataDirectory `
>> -DataDirectory Z:\ `
>> -DockerTag [yyyymmdd]
```

You should be done now! Congrats!

### Testing the Docker Image

Unfortunately, testing the docker image, due to issues with docker, isn't
possible unless you build the data directory locally. However, if you do that,
you can test it with the following command:

```pwsh
PS > Start-MsvceDockerContainer `
>> -DataDirectory [path/to/data] `
>> -DockerTag [yyyymmdd]
```

By default, you should be able to access the server at
[http://localhost:10240](http://localhost:10240). If you don't see anything,
you may need to wait a little bit. It takes about a minute to spin up.

# DataDirectory structure

To configure new compilers, you will need to install them before you can test the changes.

The DataDirectory will setup mostly by itself by using `Build-MsvceDataDirectory`,
but you will need to place the MSVC versions manually.

```
 Z:\
 |-- Msvcedata
     |-- compiler-explorer (generated)
     |-- libraries (generated)
     |-- msvc
         |-- 14.27.29111 (your new msvc folder)
             |-- bin/lib/include ... etcetera
```

So for example, if you have a Community edition of MSVC installed into something like `C:\Program Files (x86)\Microsoft Visual Studio\2019\Community\VC\Tools\MSVC\14.27.29111` - you will need to copy this path to `Z:\Msvcedata\msvc\14.27.29111`

# Other useful commands

## To list the MSVC versions that are configured

Only `msvce-config.json` is used to look these up.

```pwsh
Get-MsvceToolsetVersions
```

## To list libraries that are configured

Only `msvce-config.json` is used to look these up.

```pwsh
Get-MsvceVcpkgLibraryList
```

## To check if a specific MSVC version is detected

Note that the DataDirectory here includes the fixed foldername Msvcedata that was left out in other commands.

```pwsh
Test-MsvceToolsetExistence -DataDirectory Z:\Msvcedata -Version 1.2.1234
```

## Debugging and editing Msvce.psm1

You can pass the `-Verbose` parameter to the mentioned PS commands to enable more logging.

Should you need to make changes to Msvce.psm1 (or pulled changes from the repository), make sure you do `Import-Module -Force .\Msvce.psm1` before testing, otherwise you'll run the old version.
