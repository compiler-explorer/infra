# Adding a new MSVC compiler

We need to repackage MSVC compilers to install on the site. We do this via an actions runner.

### Finding the download URL

To get a MS compiler "built", you first need to find the right download URL

-   Head to https://visualstudio.microsoft.com/downloads/
-   Scroll down to "All Downloads" or similar
-   Open "Tools for Visual Studio"
-   There you'll find "Build Tools for Visual Studio"
-   You can find the link for "long term serviving baselines" there to get older versions
    -   Currently links to [this page](https://learn.microsoft.com/en-us/visualstudio/releases/2022/release-history#release-dates-and-build-numbers)
        which is VS 2022 specific. But from here you can snag the "build tools" Download URL for a particular version
-   You can also snag the "latest" link from the Download button, but it's probably more useful to get named releases (with their dumb version numbers, see below)

The download link will be something like `https://aka.ms/vs/17/release/vs_BuildTools.exe` (for "latest")
or `https://download.visualstudio.microsoft.com/download/pr/286c67ca-51f4-409d-ade8-3036a5184667/a8a9a3b82f278f504156a940dcfd5619e9f214eb7e9071c5f5571a0f8baa94f3/vs_BuildTools.exe` for a prior version.

### Building the package

Armed with your URL, head to [the GH action](https://github.com/compiler-explorer/infra/actions/workflows/package-ms-compiler.yaml) page. Hit "Run workflow"
and paste the URL in as the parameter.

The action runner will churn away and build the installation artifact. This takes around ten minutes.

### Checking it all works

Look in the GH action logger at the "run" step and you'll see at the end something like:

```
Everything is Ok
Uploading 14.43.34808-14.43.34810.0 ...
Uploaded 14.43.34808-14.43.34810.0 !
```

This is the actual version of the compiler that got packaged. You should be able to find this ZIP using the AWS console or

```
$ aws s3 ls s3://compiler-explorer/opt-nonfree/msvc/
```

### Installing

All the compilers live on our shared EFS, but are synced to an SMB server. Unzipping them onto the shared EFS:

Log into the admin box:

-   `aws s3 cp s3://compiler-explorer/opt-nonfree/msvc/COMPILER.ZIP /tmp`
-   `cd /efs/winshared/compilers/msvc/`
-   `unzip /tmp/COMPILER.ZIP` (will take a few miuntes)

Once unpacked, sync the smb server with `ce smb sync`. This will take a few minutes too.

### Configuring

Add a line for the compiler in the `msvc-install/gen-props.py` script; the `MSVersionSemVer` is usually the first part of the name, the `ZIPFile` is the name
of the unpacked directory, and then the `MSVSShortVer` has to be derived/guessed. Only the first two parts of the version are used as it stands, anyway.

Run the python code and then use something like `meld` to compare it against CE's `etc/config/c++.amazonwin.properties` and `etc/config/c.amazonwin.properties`.
If you run the python with `--prefix vc` it'll be more useful for comparison with c.

You can apply changes as appropriate; making sure you leave all the old stuff alone (older compilers have lots of aliases). Don't forget to add your compiler (the three versions) to the list of compilers too.

We try and keep a "latest" for each target manually up to date (`vcpp_v19_latest_x86` etc); either a "latest" being a prerelease and therefore a whole set of
compiler configuration, or else making the most recent released compiler _also_ an alias for `vcpp_v19_latest_x86`.

Deploy and test in winstaging. Remember you need to build a windows build (which probably means you need to push to main).

### For more info

See also [this doc](installing_compilers.md).
