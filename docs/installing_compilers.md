# Installing compilers

## Prerequisites

* Python 3.9 or higher
* Run `make ce` first
* The `ce` and `ce_install` scripts are in the `bin` directory, you can either set the PATH, make links or call `bin/ce` / `bin/ce_install` in the given examples below

## On Linux

The directory `/opt/compiler-explorer` is required, otherwise you'll have to supply your own destination directory and temporary staging directory to `ce_install` using `--staging-dir "/some/tmp/dir" --dest "/my/ce/dir"`

### Listing available compilers/tools

`ce_install list` or `ce_install --enable nightly list`

### Listing installation paths

To see where compilers/tools would be installed without actually installing them:

`ce_install list-paths <filter>`

Examples:
- `ce_install list-paths 'libraries/c++/fmt'` - Show all fmt library version paths
- `ce_install list-paths --absolute 'libraries/c++/fmt 10.2.1'` - Show absolute path for specific version
- `ce_install list-paths --json 'compilers/c++'` - Output all C++ compiler paths in JSON format

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
