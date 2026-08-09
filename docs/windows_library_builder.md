# Windows Library Builder

## Testing similar tasks on Local Windows

Note: do not do any of this unless you know what you're doing. It does not reflect any production situations, it just tries to mimick it.

* Create a directory where the compilers and tools will end up (e.g. `D:/efs/winshared`)
* Make a drive out of the directory with `subst Z: D:\efs\winshared`
* Install CMake and Ninja under `C:\BuildTools\CMake` and `C:\BuildTools\Ninja`, as
  `packer/InstallBuilderTools.ps1` does on the real builder
* `pwsh .\ce_install.ps1 --staging-dir "Z:/staging" --dest "Z:/compilers" --enable windows install 'mingw-w64 13.1.0-16.0.2-11.0.0-ucrt-r1'`
* `pwsh .\ce_install.ps1 --staging-dir "Z:/staging" --dest "Z:/staging" --enable windows install 'fmt 11.0.0'`
* `$env:PATH = "C:\Program Files\7-Zip;C:\BuildTools\Python;C:\BuildTools\Python\Scripts;C:\BuildTools\CMake\bin;C:\BuildTools\Ninja;Z:\compilers\windows-kits-10\bin;Z:\compilers\mingw-w64-13.1.0-16.0.2-11.0.0-ucrt-r1\bin;$env:PATH"`
* `pwsh .\ce_install.ps1 --keep-staging --dry-run --staging-dir "Z:/staging" --dest "Z:/staging" --enable windows build --temp-install --buildfor mingw64_ucrt_gcc_1130 'fmt 11.0.0'`
* `pwsh .\ce_install.ps1 --keep-staging --dry-run --staging-dir "Z:/staging" --dest "Z:/staging" --enable windows build --temp-install --buildfor vcpp_v19_40_VS17_10_x64 'fmt 11.0.0'`

## Testing On WinBuilder

* Execute contents of`init/start-builder.ps1` (outside of the GIT clone if its there)
* `pwsh .\ce_install.ps1 --staging-dir "C:/tmp/staging" --dest "C:/tmp/staging" --enable windows build --temp-install --buildfor vcpp_v19_40_VS17_10_x64 'fmt 11.0.0'`
