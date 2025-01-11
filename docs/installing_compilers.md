# Installing compilers

## Prerequisites

* Python 3.9 or higher
* Run `make ce` first
* The `ce` and `ce_install` scripts are in the `bin` directory, you can either set the PATH, make links or call `bin/ce` / `bin/ce_install` in the given examples below

## On Linux

The directory `/opt/compiler-explorer` is required, otherwise you'll have to supply your own destination directory and temporary staging directory to `ce_install` using `--staging-dir "/some/tmp/dir" --dest "/my/ce/dir"`

### Listing available compilers/tools

`ce_install list` or `ce_install --enable nightly list`

### For versioned compilers/tools

`ce_install install <name>`

For a specific version

`ce_install install '<compilername> <version>'`

### For nightlies:

`ce_install --enable nightly install <name>`

## On Windows

You can install a small amount of Windows compilers using ce_install.ps1, a regular powershell installation should be enough

`./ce_install.ps1 --staging-dir "D:/tmp/staging" --dest "D:/efs/compilers" --enable windows install windows`

### On CE infrastructure

`ce_install --staging-dir /efs/winshared/staging --dest /efs/winshared/compilers --enable windows install windows`

!no sudo!

`ce smb sync`


# Advanced testing on Windows

Note: do not do any of this unless you know what you're doing. It does not reflect any production situations, it just tries to mimick it.

* Create a directory where the compilers and tools will end up (e.g. `D:/efs/winshared`)
* Make a drive out of the directory with subst
  - `subst Z: D:\efs\winshared`
* `pwsh .\ce_install.ps1 --staging-dir "Z:/staging" --dest "Z:/compilers" --enable windows install 'windows/tools/cmake'`
* `pwsh .\ce_install.ps1 --staging-dir "Z:/staging" --dest "Z:/compilers" --enable windows install 'windows/tools/ninja'`
* `pwsh .\ce_install.ps1 --staging-dir "Z:/staging" --dest "Z:/compilers" --enable windows install 'mingw-w64 13.1.0-16.0.2-11.0.0-ucrt-r1'`
* `pwsh .\ce_install.ps1 --staging-dir "Z:/staging" --dest "Z:/staging" --enable windows install 'fmt 11.0.0'`
* `$env:PATH = "C:\BuildTools\Python;C:\BuildTools\Python\Scripts;Z:\compilers\windows-kits-10\bin;Z:\compilers\cmake-v3.29.2\bin;Z:\compilers\mingw-w64-13.1.0-16.0.5-11.0.0-ucrt-r5\bin;Z:\compilers\ninja-v1.12.1;$env:PATH"`
* `pwsh .\ce_install.ps1 --keep-staging --dry-run --staging-dir "Z:/staging" --dest "Z:/staging" --enable windows build --temp-install --buildfor mingw64_ucrt_gcc_1130 'fmt 11.0.0'`
* `pwsh .\ce_install.ps1 --keep-staging --dry-run --staging-dir "Z:/staging" --dest "Z:/staging" --enable windows build --temp-install --buildfor vcpp_v19_40_VS17_10_x64 'fmt 11.0.0'`

## On WinBuilder

`pwsh .\ce_install.ps1 --staging-dir "C:/tmp/staging" --dest "C:/tmp/staging" --enable windows build --temp-install --buildfor vcpp_v19_40_VS17_10_x64 'fmt 11.0.0'`
