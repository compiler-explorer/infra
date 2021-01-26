# MSVCE

These are the scripts which should be used to build the MSVCE data directory and
docker image.

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
shouldn't be that terrible if you just run it in the default configuration. If
you're not adding new compilers, you may pass the `-SkipVerifyToolsets` flag; if
you aren't updating vcpkg, you can pass the `-SkipVcpkgBootstrap`; and if you
aren't adding new libraries, you can pass `-SkipVcpkgLibraries`. The existing
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
