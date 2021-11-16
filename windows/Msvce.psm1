#Requires -Version 6.0

# TODO: add a parameter to all the cmdlets to allow people to change the
# config path
$CONFIG_PATH = "$PSScriptRoot\msvce-config.json"
$VCPKG_PATH = "$PSScriptRoot\vcpkg"
$BUILD_PATH = "$PSScriptRoot\docker"

Set-StrictMode -Version 2

<#
.SYNOPSIS

Gets config:$JPath.

.DESCRIPTION

Parses the config file at msvce-config.json inside the root directory, or $Path
if it's passed in, and then accesses $JPath in the resulting parsed object.

Treats non-existent paths as null, so that if the final element of the JPath
leads nowhere, one gets null; otherwise, one gets a null method receiver error.

.PARAMETER JPath

A slash (forward or backward) separated path into the JSon. If an object at a
specific path is an array, Get-MsvceConfig attempts to index at the integer
value of the path. If Get-MsvceConfig is called with a null JPath, or with no
JPath, then it returns the entire config object.

.PARAMETER Path

The path to the msvce-config.json file. By default, uses msvce-config.json in
the script root.

.INPUTS

System.String
  A string representation of a JSON object.

.OUTPUTS

Object, Object[], System.String, Int64, Double
  The value at the specified $JPath

.NOTES

Get-MsvceConfig is mostly external for debugging purposes, and if you're curious
about the config file.

Eventually, this cmdlet _should_ check against the schema of the file, if any;
unfortunately, Test-Json's schema support is currently buggy as all heck, and
so we can't.

--- Example 1 ---

PS> $conf = '{"x": ["y", {"z": "foo"}]}'
PS> Get-MsvceConfig -Content $conf 'x/0'
y
PS> Get-MsvceConfig -Content $conf 'x/1'

Name                           Value
----                           -----
z                              foo

PS> Get-MsvceConfig -Content $conf 'x/1/z'
foo

.LINK
Build-MsvceDockerImage
.LINK
Build-MsvceDataDirectory
.LINK
Publish-MsvceDataDirectory
#>
function Get-MsvceConfig {
  [CmdletBinding(PositionalBinding=$false, DefaultParameterSetName='Path')]
  Param(
    [Parameter(Mandatory=$false, Position=0)]
    [string]$JPath,

    [Parameter(Mandatory=$false, ParameterSetName='Path')]
    [ValidateScript({Test-Path -LiteralPath $_ -PathType 'Leaf'})]
    [string]$Path = $CONFIG_PATH,

    [Parameter(
      Mandatory=$true,
      ParameterSetName='Content',
      ValueFromPipeline)]
    [string]$Content
  )

  if ([string]::IsNullOrEmpty($Content)) {
    $Content = Get-Content -LiteralPath $Path
  }

  $json = $Content | ConvertFrom-Json -AsHashtable

  if (-not [string]::IsNullOrEmpty($JPath)) {
    $JPath -split '[/\\]' | ForEach-Object {
      if ($null -eq $json) {
        throw "Invalid path: $JPath"
      }
      $json = $json[$_]
    }
  }

  return $json
}

<#
.SYNOPSIS

Build the docker image for MSVCE: CE, Node, and the Windows SDK are included.

.DESCRIPTION

Build-MsvceDockerImage can work in one of two modes -- Setup mode, where it does
everything for you (this is the mode you should usually use), and NoSetup mode.

When in Setup mode, it creates a temporary directory, then:
  - Downloads Node, CE, and the Windows SDK into this directory
  - Builds the Dockerfile based on the information in those three items
  - runs `docker build`

When in NoSetup mode, it only does the last bit, in $BuildDirectory.

.PARAMETER WindowsVersion

Windows Server Core version to use as a base. Defaults to config:windows/version

.PARAMETER DockerTag

The tag used to name the docker image. Defaults to 'test', i.e., 'msvce:test'

.PARAMETER BuildDirectory

Use this directory to build the docker image, instead of the default,
'$PSScriptRoot/docker'.

.PARAMETER Clean

Clean out the build directory before running setup.

.PARAMETER JustBuild

Not useful in general, but if you're doing manual setup of the output directory,
then pass this to only do a build of the existing output directory.

.PARAMETER GitCommit

The specific hash of compiler-explorer to use for building the image. Use
'main' for the latest on github. Any value is okay to use for testing, but
images uploaded to production server need to be registered with
https://ossmsft.visualstudio.com/_oss

.PARAMETER NodeVersion

Use the specified nodejs version instead of the default.

.INPUTS

None
  This cmdlet does not accept any input.

.OUTPUTS

None
  This cmdlet does not generate any output.

.NOTES

Normally, one should just use Setup mode; follow the example.

-----------------------------Example 1: Normal Use------------------------------
PS > Build-MsvceDockerImage

This will build a docker image with tag 'test'. One can then tag the docker
image how you want with

PS > docker tag msvce:test msvce:<tag-name>

.LINK
Build-MsvceDataDirectory
.LINK
Publish-MsvceDataDirectory
.LINK
Build-Template
.LINK
Get-MsvceNode
.LINK
Get-MsvceCompilerExplorer
.LINK
Get-MsvceWindowsSdk
.LINK
https://ossmsft.visualstudio.com/_oss
#>
function Build-MsvceDockerImage
{
  [CmdletBinding(PositionalBinding=$false)]
  Param(
    [Parameter(Mandatory=$false, ParameterSetName='Setup')]
    [string]$WindowsVersion = (Get-MsvceConfig 'windows/version'),

    [Parameter(Mandatory=$false)]
    [string]$DockerTag = 'test',

    [Parameter(Mandatory=$false)]
    [string]$BuildDirectory = $BUILD_PATH,

    [Parameter(Mandatory=$false, ParameterSetName='Setup')]
    [switch]$Clean,

    [Parameter(Mandatory=$true, ParameterSetName='NoSetup')]
    [switch]$JustBuild,

    [Parameter(Mandatory=$false)]
    [string]$GitCommit = (Get-MsvceConfig 'compiler_explorer/git_commit'),

    [Parameter(Mandatory=$false)]
    [string]$NodeVersion = (Get-MsvceConfig 'node/version'),

    [Parameter(Mandatory=$false, DontShow)]
    [string]$NodeArchitecture = (Get-MsvceConfig 'node/architecture')
  )

  $ErrorActionPreference = 'Stop'

  if (-not $JustBuild) {
    if ($Clean -and (Test-Path -LiteralPath $BuildDirectory)) {
      Write-Verbose "Cleaning build directory '$BuildDirectory'"
      Remove-Item -Recurse -Force -LiteralPath $BuildDirectory
    }
    if (-not (Test-Path $BuildDirectory)) {
      Write-Verbose "Creating build directory '$BuildDirectory'"
      New-Item -Path $BuildDirectory -ItemType 'directory' | Out-Null
    }

    if (Test-Path -LiteralPath "$BuildDirectory/node") {
      Write-Verbose "Using existing node in $BuildDirectory"
    } else {
      Get-MsvceNode `
        -BuildDirectory $BuildDirectory `
        -NodeVersion $NodeVersion `
        -NodeArchitecture $NodeArchitecture
    }

    Get-MsvceCompilerExplorer `
      -BuildDirectory $BuildDirectory `
      -GitCommit $GitCommit

    Get-MsvceWindowsSdk -BuildDirectory $BuildDirectory

    Build-Template `
      -InFile "$PSScriptRoot\files\Dockerfile.template" `
      -OutFile "$BuildDirectory\Dockerfile" `
      -Bindings @{ WindowsVersion = $WindowsVersion } `
      | Out-Null
  }

  Write-Verbose "Building docker image"
  docker build $BuildDirectory -t "msvce:$DockerTag"

  if (-not $?) {
    throw 'Docker build failed'
  }
}

<#
.SYNOPSIS

Downloads one commit of Compiler Explorer from git into the build directory.

.DESCRIPTION

First clones the Compiler Explorer github repository, then checks out the
specific commit which was passed, or the default, which is pinned. Then, it
removes all other information in order to create the smallest possible build
directory.

.PARAMETER InFile

The  template file to build.

.PARAMETER OutFile

The file to write the built template to.

.PARAMETER Bindings

The bindings one replaces; in the template file, `{Asdf}` is replaced by
`$Bindings.Asdf`.

.INPUTS

None
  This cmdlet does not accept any input.

.OUTPUTS

System.Object
  This cmdlet returns the file it creates.

.NOTES

This is a utility for building a final file from a template file. It replaces
variables inside curly braces with a value from the Bindings variable. For
example, given a file:

  Hello, my name is {Name}.

with Bindings:

  @{ Name = 'Nicole' }

will result in the following file:

  Hello, my name is Nicole.

If one wishes to put a literal curly brace in a file, one can use doubled
braces; i.e.,

  {{ "asdf": "qwerty" }}

will result in

  { "asdf": "qwerty" }

.LINK
Build-MsvceDockerImage
.LINK
Get-MsvceNode
.LINK
Get-MsvceCompilerExplorer
.LINK
Get-MsvceWindowsSdk
#>
function Build-Template {
  [CmdletBinding(PositionalBinding=$false)]
  Param(
    [Parameter(Mandatory=$true)]
    [ValidateScript({Test-Path -LiteralPath $_ -PathType 'Leaf'})]
    [string]$InFile,

    [Parameter(Mandatory=$true)]
    [string]$OutFile,

    [Parameter(Mandatory=$true)]
    [Hashtable]$Bindings
  )

  if (Test-Path -LiteralPath $OutFile) {
    Write-Verbose "Removing existing dockerfile"
    Remove-Item -LiteralPath $OutFile
  }

  Write-Verbose "Writing templated Dockerfile to $OutFile"

  [string[]]$file = @()
  [string[]]$template = Get-Content -LiteralPath $InFile

  $template | ForEach-Object {
    $line = [System.Text.StringBuilder]::new()
    for ($idx = 0; $idx -lt $_.Length; ++$idx) {
      if ($_[$idx] -eq '{') {
        if ($_[$idx + 1] -eq '{') {
          $line.Append('{') | Out-Null
          ++$idx
        } else {
          $first = $idx + 1
          while ($_[$idx] -ne '}') {
            if ($idx -ge $_.Length) {
              throw "Invalid line: Open brace '{' without a close brace '}': `n$_"
            }
            ++$idx
          }
          $var = $_.Substring($first, $idx - $first)
          if ($Bindings.Contains($var)) {
            $line.Append($Bindings.$var) | Out-Null
          } else {
            throw "Template variable not in Bindings map: $var"
          }
        }
      } elseif ($_[$idx] -eq '}') {
        if ($_[$idx + 1] -eq '}') {
          $line.Append('}') | Out-Null
          ++$idx
        } else {
          throw "Invalid line: Close brace '}' without an open brace '{':`n$_"
        }
      } else {
        $line.Append($_[$idx]) | Out-Null
      }
    }
    $file += $line.ToString()
  }

  return New-Item `
    -Path $OutFile `
    -Value ($file -join "`n")
}

<#
.SYNOPSIS

Downloads node.js from node's website, and extracts it into $BuildDirectory.

.DESCRIPTION

Downloads node.zip, version $NodeVersion, into $BuildDirectory, then extracts it
into $BuildDirectory\node.

.PARAMETER BuildDirectory

The directory to place node.js in.

.PARAMETER NodeVersion

The version of node.js to download. Defaults to config:node/version

.INPUTS

None
  This cmdlet does not accept any input.

.OUTPUTS

None
  This cmdlet does not generate any output.

.NOTES

This cmdlet is for debug use only. Generally, one should use
Build-MsvceDockerImage to do everything.

.LINK
Build-MsvceDockerImage
.LINK
Build-Template
.LINK
Get-MsvceCompilerExplorer
.LINK
Get-MsvceWindowsSdk
#>
function Get-MsvceNode {
  [CmdletBinding(PositionalBinding=$false)]
  Param(
    [Parameter(Mandatory=$true, Position=0)]
    [ValidateScript({Test-Path -LiteralPath $_ -PathType 'Container'})]
    [string]$BuildDirectory,

    [Parameter(Mandatory=$false)]
    [string]$NodeVersion = (Get-MsvceConfig 'node/version'),

    [Parameter(Mandatory=$false, DontShow)]
    [string]$NodeArchitecture = (Get-MsvceConfig 'node/architecture')
  )

  $nodeName = "node-v$NodeVersion-$NodeArchitecture"
  $uri = "https://nodejs.org/dist/v$NodeVersion/$nodeName.zip"

  if (Test-Path -LiteralPath "$BuildDirectory\node") {
    Write-Verbose 'Removing existing node directory'
    Remove-Item -Recurse -LiteralPath "$BuildDirectory\node"
  }

  Write-Verbose "Downloading node.zip (version $NodeVersion) from internet"
  Invoke-WebRequest `
    -Uri $uri `
    -OutFile "$BuildDirectory\node.zip"

  if (
    $NodeVersion -eq (Get-MsvceConfig 'node/version') `
    -and $NodeArchitecture -eq (Get-MsvceConfig 'node/architecture'))
  {
    $fileHash = (Get-FileHash "$BuildDirectory\node.zip").Hash
    if ($fileHash -ne (Get-MsvceConfig 'node/hash')) {
      Write-Error "Hash of Node version $NodeVersion doesn't match:
expected: $(Get-MsvceConfig 'node/hash')
actual: $fileHash"
    }
  }

  Write-Verbose 'Decompressing node.zip -- this may take a while'
  [System.IO.Compression.ZipFile]::ExtractToDirectory( `
    "$BuildDirectory\node.zip", "$BuildDirectory")
  Write-Verbose 'Decompressing is done'

  Move-Item `
    -LiteralPath "$BuildDirectory\$nodeName" `
    -Destination "$BuildDirectory\node"

  Remove-Item -LiteralPath "$BuildDirectory\node.zip"
}

<#
.SYNOPSIS

Downloads one commit of Compiler Explorer from git into the build directory.

.DESCRIPTION

First clones the Compiler Explorer github repository, then checks out the
specific commit which was passed, or the default, which is pinned. Then, it
removes all other information in order to create the smallest possible build
directory.

.PARAMETER BuildDirectory

The directory to download the Compiler Explorer directory into.

.PARAMETER GitCommit

The specific git commit to check out. Defaults to a pinned version.

.INPUTS

None
  This cmdlet does not accept any input.

.OUTPUTS

None
  This cmdlet does not generate any output.

.NOTES

This cmdlet is for debug use only. Generally, one should use
Build-MsvceDockerImage to do everything.

.LINK
Build-MsvceDockerImage
.LINK
Build-Template
.LINK
Get-MsvceNode
.LINK
Get-MsvceWindowsSdk
#>
function Get-MsvceCompilerExplorer {
  [CmdletBinding(PositionalBinding=$false)]
  Param(
    [Parameter(Mandatory=$true, Position=0)]
    [ValidateScript({Test-Path -LiteralPath $_ -PathType 'Container'})]
    [string]$BuildDirectory,

    [Parameter(Mandatory=$false)]
    [string]$GitCommit = (Get-MsvceConfig 'compiler_explorer/git_commit')
  )

  if ($GitCommit -ne (Get-MsvceConfig 'compiler_explorer/git_commit'))
  {
    Write-Warning 'The hash in GitCommit must be registered with oss tool before uploading to production server.'
    Write-Warning 'See https://ossmsft.visualstudio.com/_oss'
  }

  $BuildDirectory = (Get-Item -LiteralPath $BuildDirectory).FullName

  # we have a temporary git dir so that we can take _only_ the commit we need
  # into the docker container. This means that we don't have to have a giant
  # container full of all the versions of compiler explorer
  $gitDir = "$BuildDirectory\compiler-explorer"
  $temporaryGitDir = "$gitDir.tmp"

  if (Test-Path -LiteralPath $gitDir) {
    Push-Location -LiteralPath $gitDir
    $revision = git rev-list HEAD --max-count=1
    Pop-Location
    if ($GitCommit -eq $revision) {
      Write-Verbose 'Compiler Explorer git repository is already set up'
      return
    } else {
      Write-Verbose 'Compiler Explorer git repository is on the wrong commit -- removing'
      Remove-Item -Force -Recurse -LiteralPath $gitDir
    }
  }

  Write-Verbose 'Cloning original compiler explorer repository'
  git clone --quiet -- `
    (Get-MsvceConfig 'compiler_explorer/git_url') `
    $temporaryGitDir
  git init --quiet $gitDir

  Write-Verbose "Tagging commit $GitCommit"
  Push-Location $temporaryGitDir
  git tag -m 'MSVCE commit' msvce $GitCommit
  Pop-Location

  Write-Verbose 'Fetching commit into final directory'
  Push-Location $gitDir
  git remote add origin $temporaryGitDir
  git fetch --quiet --depth 1 origin refs/tags/msvce
  git reset --quiet --hard FETCH_HEAD
  Pop-Location

  Write-Verbose 'Removing unnecessary files'
  Remove-Item -Recurse -Force -LiteralPath $temporaryGitDir

  Write-Verbose 'Writing down the git hash so that CE can read it'
  # Create directories
  New-Item -Path "$gitDir/out/dist" -ItemType 'Directory' -Force
  New-Item `
    -Path "$gitDir/out/dist/git_hash" `
    -ItemType 'File' `
    -Value $GitCommit `
    | Out-Null
}

<#
.SYNOPSIS

Downloads the Windows SDK installer into the build directory.

.DESCRIPTION

Downloads a pinned version of the Windows SDK from the Microsoft website. The
link is taken from config:windows_sdk/link, and the hash of this file is checked
against config:windows_sdk/hash.

.PARAMETER BuildDirectory

The directory to download the installer into.

.INPUTS

None
  This cmdlet does not accept any input.

.OUTPUTS

None
  This cmdlet does not generate any output.

.NOTES

This cmdlet is for debug use only. Generally, one should use
Build-MsvceDockerImage to do everything.

.LINK
Build-MsvceDockerImage
.LINK
Build-Template
.LINK
Get-MsvceCompilerExplorer
.LINK
Get-MsvceNode
#>
function Get-MsvceWindowsSdk {
  [CmdletBinding(PositionalBinding=$false)]
  Param(
    [Parameter(Mandatory=$true, Position=0)]
    [string]$BuildDirectory
  )

  if (Test-Path -LiteralPath "$BuildDirectory\winsdksetup.exe") {
    $sdkHash = (Get-FileHash -LiteralPath "$BuildDirectory\winsdksetup.exe").Hash
    if ($sdkHash -eq (Get-MsvceConfig 'windows_sdk/hash')) {
      Write-Verbose 'winsdksetup.exe exists, and has the correct hash; skipping download'
      return
    } else {
      Write-Verbose 'Removing existing Windows SDK'
      Remove-Item -LiteralPath "$BuildDirectory\winsdksetup.exe"
    }
  }
  Invoke-WebRequest `
    -Uri (Get-MsvceConfig 'windows_sdk/link') `
    -OutFile "$BuildDirectory\winsdksetup.exe"

  $sdkHash = (Get-FileHash "$BuildDirectory\winsdksetup.exe").Hash
  if ($sdkHash -ne (Get-MsvceConfig 'windows_sdk/hash')) {
    Write-Error `
      "winsdksetup.exe downloaded from $SDK_LINK has incorrect hash:
expected: $(Get-MsvceConfig 'windows_sdk/hash')
actual: $sdkHash"
  }
}



<#
.SYNOPSIS

Builds the directory which MSVCE uses for compilers, libraries, and
configuration.

.DESCRIPTION

Build-MsvceDataDirectory incrementally builds the MSVCE data directory in
$DataDirectory.

Builds the following data directory:

$DataDirectory\
  compiler-explorer\
    ... configuration files ...
  msvc\
    config:toolset/package_name.$Version/
      ... data ...
  vcpkg\
    ... exported vcpkg libraries ...

.PARAMETER DataDirectory

The directory which MSVCE can use as its C:\data.

.PARAMETER DockerTag

The tag which was used to build the docker image with Build-MsvceDockerImage.
Required because of the Windows SDK.

.PARAMETER Clean

Clear out the existing $DataDirectory. By default, Build-MsvceDataDirectory
works incrementally.

.INPUTS

None
  You cannot pipe objects to Build-MsvceDataDirectory

.OUTPUTS

System.Object
  Build-MsvceDataDirectory returns the directory it did its work in

.NOTES

The MSVCE functions are designed to be easy to use. If you don't need any
special usecase, you can follow example 1 fairly easily.

---------------------------- Example 1: Normal Use -----------------------------

PS> Build-MsvceDataDirectory -DataDirectory .\data -DockerTag test

.LINK
Build-MsvceDockerImage
.LINK
Publish-MsvceDataDirectory
.LINK
Get-MsvceToolsetPrettyName
.LINK
Install-MsvceBaseCEFiles
.LINK
Install-MsvceConfigurationFile
.LINK
Test-MsvceToolsetExistence
.LINK
https://developer.microsoft.com/en-US/windows/downloads/windows-10-sdk
#>
function Build-MsvceDataDirectory {
  [CmdletBinding(PositionalBinding=$false)]
  Param(
    [Parameter(Mandatory=$true, Position=0)]
    [string]$DataDirectory,

    [Parameter(Mandatory=$true)]
    [string]$DockerTag,

    [Parameter(Mandatory=$false)]
    [switch]$SkipVerifyToolsets,

    [Parameter(Mandatory=$false)]
    [switch]$CleanVcpkgDirectory,

    [Parameter(Mandatory=$false)]
    [switch]$SkipVcpkgLibraries,

    [Parameter(Mandatory=$false)]
    [switch]$SkipVcpkgBootstrap,

    [Parameter(Mandatory=$false)]
    [switch]$Clean
  )

  $ErrorActionPreference = 'Stop'

  if ($Clean -and (Test-Path -LiteralPath $DataDirectory)) {
    Write-Verbose "Cleaning $DataDirectory"
    Remove-Item -Recurse $DataDirectory
  }

  if ($CleanVcpkgDirectory -and (Test-Path -LiteralPath $VCPKG_PATH)) {
    Write-Verbose "Cleaning $VCPKG_PATH"
    Remove-Item -Recurse -Force $VCPKG_PATH
  }

  if (-not (Test-Path -LiteralPath $DataDirectory -PathType 'Container')) {
    Write-Verbose "Creating the $DataDirectory directory"
    New-Item -Path $DataDirectory -ItemType 'Directory' | Out-Null
  }

  if (-not $SkipVerifyToolsets) {
    Write-Verbose "Verifying MSVCE toolsets"

    $versions = Get-MsvceToolsetVersions

    if (Test-Path "$DataDirectory\msvc") {
      Get-ChildItem -Name "$DataDirectory\msvc" | ForEach-Object {
        if ($_ -notin $versions) {
          Write-Warning "Msvc toolset not present in msvce-config.json is found at: $DataDirectory\msvc\$_"
        } else {
          Write-Verbose "Msvc toolset at: $DataDirectory\msvc\$_"
        }
      }
    }

    $versions | ForEach-Object {
      $exists = Test-MsvceToolsetExistence `
        -DataDirectory $DataDirectory `
        -Version $_

      if (-not $exists) {
        Write-Warning "Msvc toolset $_ present in msvce-config.json is missing from DataDirectory: $DataDirectory"
      }
    }
  }

  if (-not $SkipVcpkgLibraries) {
    Write-Verbose 'Initializing vcpkg'
    Initialize-MsvceVcpkg -SkipVcpkgBootstrap:$SkipVcpkgBootstrap

    Write-Host 'Installing the necessary vcpkg libraries'
    Write-Host "This may take a while (> 2 hours), especially if you haven't done this before, or if you upgraded vcpkg"
    Build-MsvceVcpkgLibraries
    Install-MsvceVcpkgLibraries -DataDirectory $DataDirectory
  }

  Write-Verbose 'Installing MSVCE base CE files'
  Install-MsvceBaseCEFiles -DataDirectory $DataDirectory

  Write-Verbose 'Installing MSVCE C++ configuration file'
  Install-MsvceConfigurationFile `
    -DataDirectory $DataDirectory `
    -DockerTag $DockerTag `
    | Out-Null

  Write-Verbose 'Installing MSVCE C configuration file'
  Install-MsvceConfigurationFile `
    -DataDirectory $DataDirectory `
    -DockerTag $DockerTag `
    -CProperties `
    | Out-Null
}

<#
.SYNOPSIS

Gets all the versions of the toolset that the config file supports

.DESCRIPTION

Get-MsvceToolsetVersions returns all versions of the toolset that the config
file has listed, not necessarily all of the versions of the toolset that are
installed. In other words, the keys of config:toolset/versions.

.INPUTS
None
  This cmdlet does not accept any input.

.OUTPUTS
System.String[]
  The versions of the compiler listed in config:toolset/versions


.NOTES

This cmdlet is for debug use only. Generally, one should use
Build-MsvceDataDirectory to do everything.

.LINK
Build-MsvceDataDirectory
.LINK
Get-MsvceToolsetVersions
.LINK
Get-MsvceToolsetPrettyName
.LINK
Install-MsvceBaseCEFiles
.LINK
Install-MsvceConfigurationFile
.LINK
Test-MsvceToolsetExistence
#>
function Get-MsvceToolsetVersions {
  [OutputType([string[]])]
  [CmdletBinding()]
  param()

  Get-MsvceConfig 'toolset' | ForEach-Object { $_.version }
}

<#
#>
function Get-MsvceToolset {
  [CmdletBinding()]
  param(
    [string]$Version
  )

  $toolset = Get-MsvceConfig "toolset" | Where-Object { $_.version -eq $Version }
  if ($null -eq $toolset) {
    Write-Error "Version $Version not found; this should not be possible"
    throw;
  }
  if (@($toolset).Length -gt 1) {
    Write-Error "There were multiple records corresponding to version $Version; this shouldn't be possible"
    $toolset = $toolset[0]
  }

  return $toolset
}

<#
.SYNOPSIS

Gets the pretty name of a specific compiler version.

.DESCRIPTION

Returns config:toolset/versions/$Version. If that path does not exist, warns
and returns $Version.

.PARAMETER Version

The version whose pretty name to get.

.INPUTS

System.String
  $Version

.OUTPUTS

System.String
  The pretty name of $Version

.NOTES

This cmdlet is for debug use only. Generally, one should use
Build-MsvceDataDirectory to do everything.

.LINK
Build-MsvceDataDirectory
.LINK
Get-MsvceToolsetVersions
.LINK
Get-MsvceToolsetPrettyName
.LINK
Install-MsvceBaseCEFiles
.LINK
Install-MsvceConfigurationFile
.LINK
Test-MsvceToolsetExistence
#>
function Get-MsvceToolsetPrettyName {
  [CmdletBinding()]
  Param(
    [Parameter(Mandatory=$true, ValueFromPipeline)]
    [string]$Version
  )

  $toolset = Get-MsvceToolset $Version
  Write-Verbose "The pretty name for $($toolset.version) is $($toolset.pretty)"
  return $toolset.pretty
}

<#
.SYNOPSIS

Checks for the existence of a specific toolset inside the data directory.

.DESCRIPTION

Test-MsvceToolsetExistence checks for a specific version of the toolset in the
data directory, to see if one should include it in the CE config file.

.PARAMETER DataDirectory

The directory which MSVCE can use as its C:\Data.

.PARAMETER Version

The version of the toolset to test for.

.INPUTS

None
  This cmdlet does not accept any input.

.OUTPUTS

bool
  Whether the toolset exists.

.NOTES

This cmdlet is for debug use only. Generally, one should use
Build-MsvceDataDirectory to do everything.

.LINK
Build-MsvceDataDirectory
.LINK
Get-MsvceToolsetVersions
.LINK
Get-MsvceToolsetPrettyName
.LINK
Install-MsvceBaseCEFiles
.LINK
Install-MsvceConfigurationFile
.LINK
Test-MsvceToolsetExistence
#>
function Test-MsvceToolsetExistence {
  [CmdletBinding(PositionalBinding=$false)]
  Param(
    [Parameter(Mandatory=$true)]
    [string]$DataDirectory,

    [Parameter(Mandatory=$true, ValueFromPipeline=$true)]
    [string[]]$Version
  )

  Process {
    $exists = Test-Path `
      -LiteralPath "$DataDirectory\msvc\$Version" `
      -PathType 'Container'

    $exists
  }
}

<#
.SYNOPSIS

Initializes the vcpkg directory for use.

.DESCRIPTION

Initialize-MsvceVcpkg initializes the specified vcpkg directory to the specified
tag or commit, or uses the existing commit that is there. If the directory does
not exist, it is created first, pointed at config:vcpkg/url

.PARAMETER VcpkgDirectory

The directory where vcpkg should live -- by default, $PSScriptRoot/vcpkg.

.PARAMETER Tag

The tag to check out from the remote tree. Defaults to config:vcpkg/release.
Assumes that the tree where the tags live is at the remote 'origin'.

.PARAMETER CommitOrBranch

The commit or branch to check out from the remote tree. Assumes that the
tree where that commit or branch exists is at the remote 'origin'.

.PARAMETER UseCurrentCommit

Pass this parameter to cause this script to do nothing except bootstrap vcpkg.

.INPUTS

None
  This cmdlet does not accept any input.

.OUTPUTS

None
  This cmdlet does not generate any output.

.NOTES

This cmdlet is for debug use only. Generally, one should use
Build-MsvceDataDirectory to do everything.

.LINK
Build-MsvceDataDirectory
.LINK
Get-MsvceToolsetVersions
.LINK
Get-MsvceToolsetPrettyName
.LINK
Install-MsvceBaseCEFiles
.LINK
Install-MsvceConfigurationFile
.LINK
Test-MsvceToolsetExistence
#>
function Initialize-MsvceVcpkg {
  [CmdletBinding(PositionalBinding=$false, DefaultParameterSetName='TaggedCommit')]
  param(
    [Parameter(Mandatory=$false)]
    [string]$VcpkgDirectory = $VCPKG_PATH,

    [Parameter(Mandatory=$false, ParameterSetName='TaggedCommit')]
    [string]$Tag = (Get-MsvceConfig 'vcpkg/release'),

    [Parameter(Mandatory=$true, ParameterSetName='SelectCommit')]
    [string]$CommitOrBranch,

    [Parameter(Mandatory=$true, ParameterSetName='CurrentCommit')]
    [switch]$UseCurrentCommit,

    [Parameter(Mandatory=$false)]
    [switch]$SkipVcpkgBootstrap
  )

  if (-not (Test-Path -LiteralPath $VcpkgDirectory)) {
    if ($UseCurrentCommit) {
      throw "Attempted to use the current commit of a vcpkg directory that doesn't exist: $VcpkgDirectory"
    }

    git init $VcpkgDirectory | Write-Verbose
    if (-not $?) {
      throw "git init failed"
    }

    Push-Location -LiteralPath $VcpkgDirectory
    $gitUrl = Get-MsvceConfig 'vcpkg/url'
    git remote add origin $gitUrl | Write-Verbose
    if (-not $?) {
      throw "git remote add origin $gitUrl failed"
    }
    Pop-Location
  }

  Push-Location -LiteralPath $VcpkgDirectory
  if (-not [string]::IsNullOrEmpty($CommitOrBranch)) {
    git fetch origin | Write-Verbose
    if (-not $?) {
      throw "git fetch origin failed"
    }

    git checkout $CommitOrBranch | Write-Verbose
    if (-not $?) {
      throw "git checkout $CommitOrBranch failed"
    }
  } elseif (-not $UseCurrentCommit) {
    # in the case of $UseCurrentCommit there's nothing we have to do
    git fetch --depth 1 origin "refs/tags/$Tag" | Write-Verbose
    git reset --hard FETCH_HEAD | Write-Verbose
  }
  Pop-Location

  # we are now at the correct commit
  if (-not $SkipVcpkgBootstrap) {
    Write-Verbose 'Bootstrapping vcpkg'
    & "$VcpkgDirectory/bootstrap-vcpkg.bat" | Write-Verbose
  }
}

<#
.SYNOPSIS

Turns a list of libraries into a list of targets for vcpkg.

.DESCRIPTION

Get-MsvceVcpkgLibraryList takes an array of libraries, which are either strings,
or hashmaps, and takes the list of architectures from
config:vcpkg/architectures, and creates an array of targets suitable to be
passed to vcpkg install, export, or whatever.

.PARAMETER Libraries

The libraries which one wishes to create targets of. The keys of this hashtable
should be the libraries to install from vcpkg, and the values should be either
null (in which case the library will not be installed), or should have the keys:
  - pretty_name: the name of the library in the MSVCE UI
  - [optional] architectures: array of architectures to install on

If architectures is not specified, then the library is installed for all
architectures listed in config:vcpkg/architectures.

.INPUTS

none
  This cmdlet does not accept any input.

.OUTPUTS

string[]
  The targets for vcpkg to ingest.

.NOTES

This cmdlet is for debug use only. Generally, one should use
Build-MsvceDataDirectory to do everything.

.LINK
Build-MsvceDataDirectory
.LINK
Get-MsvceToolsetVersions
.LINK
Get-MsvceToolsetPrettyName
.LINK
Install-MsvceBaseCEFiles
.LINK
Install-MsvceConfigurationFile
.LINK
Test-MsvceToolsetExistence
#>
function Get-MsvceVcpkgLibraryList {
  [CmdletBinding(PositionalBinding=$false)]
  param(
    [Parameter(Mandatory=$false, Position=0)]
    [hashtable]$Libraries = (Get-MsvceConfig 'vcpkg/libraries')
  )

  Begin {
    function VcpkgArchName {
      param($Arch)

      return Get-MsvceConfig "vcpkg/architectures/$Arch"
    }

    $AllArchitectures = (Get-MsvceConfig 'vcpkg/architectures').Keys
  }

  Process {
    $Libraries.GetEnumerator() | ForEach-Object {
      if ($null -eq $_.Value) {
        return
      }

      $libraryName = $_.Name
      if (-not $libraryName.StartsWith('$')) {
        if ($_.Value.ContainsKey('architectures')) {
          [array]$architectures = $_.Value.architectures
        } else {
          [array]$architectures = $AllArchitectures
        }

        $architectures | ForEach-Object {
          "${libraryName}:$(VcpkgArchName $_)"
        }
      }
    }
  }
}

<#
.SYNOPSIS

Builds the libraries which will be installed into the data directory.

.DESCRIPTION

Build-MsvceVcpkgLibraries reads config:vcpkg/libraries to discover which
libraries and architectures which it should `vcpkg install`, and then installs
them. After running this command, one can use Install-MsvceVcpkgLibraries to
actually install them into the data directory.

.PARAMETER VcpkgDirectory

The directory where vcpkg lives -- by default, $PSScriptRoot/vcpkg, which is
where Initialize-MsvceVcpkg will default to as well.

.PARAMETER Libraries

Instead of reading config:vcpkg/libraries to discover which libraries and
architectures to install, uses this parameter. Read the documentation of
Get-MsvceVcpkgLibraryList to discover the shape of this parameter.

.INPUTS

array
  The specific libraries to install.

.OUTPUTS

None
  This cmdlet does not generate any output.

.NOTES

This cmdlet is for debug use only. Generally, one should use
Build-MsvceDataDirectory to do everything.

.LINK
Build-MsvceDataDirectory
.LINK
Get-MsvceToolsetVersions
.LINK
Get-MsvceToolsetPrettyName
.LINK
Install-MsvceBaseCEFiles
.LINK
Install-MsvceConfigurationFile
.LINK
Test-MsvceToolsetExistence
#>
function Build-MsvceVcpkgLibraries {
  [CmdletBinding(PositionalBinding=$false)]
  param(
    [Parameter(Mandatory=$false, Position=0)]
    [hashtable]$Libraries = (Get-MsvceConfig 'vcpkg/libraries'),

    [Parameter(Mandatory=$false)]
    [string]$VcpkgDirectory = $VCPKG_PATH
  )

  if (-not (Test-Path -LiteralPath "$VcpkgDirectory/vcpkg.exe")) {
    throw 'First call Initialize-MsvceVcpkg before Build-MsvceVcpkgLibraries'
  }

  function BuildLibrary {
    param($Name)

    & "$VcpkgDirectory/vcpkg.exe" install "$Name" | Write-Verbose
    if (-not $?) {
      throw "vpckg build failed on library $Name"
    }
  }

  Get-MsvceVcpkgLibraryList $Libraries | ForEach-Object {
    Write-Verbose "Building $_"
    BuildLibrary -Name $_
  }
}

<#
.SYNOPSIS

Installs the specified libraries into the data directory.

.DESCRIPTION

Install-MsvceVcpkgLibraries uses `vcpkg export` to install the specified
libraries into the data directory.

.PARAMETER DataDirectory

The directory which MSVCE can use as its C:\Data.

.PARAMETER VcpkgDirectory

The directory to use for vcpkg. Defaults to '$PSScriptRoot/vcpkg'.

.PARAMETER Libraries

Instead of reading config:vcpkg/libraries to discover which libraries and
architectures to install, uses this parameter. Read the documentation of
Get-MsvceVcpkgLibraryList to discover the shape of this parameter.

.INPUTS

array
  The specific libraries to install.

.OUTPUTS

None
  This cmdlet does not generate any output.

.NOTES

This cmdlet is for debug use only. Generally, one should use
Build-MsvceDataDirectory to do everything.

.LINK
Build-MsvceDataDirectory
.LINK
Get-MsvceToolsetVersions
.LINK
Get-MsvceToolsetPrettyName
.LINK
Install-MsvceBaseCEFiles
.LINK
Install-MsvceConfigurationFile
.LINK
Test-MsvceToolsetExistence
#>
function Install-MsvceVcpkgLibraries {
  [CmdletBinding(PositionalBinding=$false)]
  param(
    [Parameter(Mandatory=$false, Position=0)]
    [hashtable]$Libraries = (Get-MsvceConfig 'vcpkg/libraries'),

    [Parameter(Mandatory=$true)]
    [string]$DataDirectory,

    [Parameter(Mandatory=$false)]
    [string]$VcpkgDirectory = $VCPKG_PATH
  )

  if (-not (Test-Path -LiteralPath "$VcpkgDirectory/vcpkg.exe")) {
    throw 'First call Initialize-MsvceVcpkg before Install-MsvceVcpkgLibraries'
  }

  & "$VcpkgDirectory/vcpkg.exe" export `
    --raw `
    "--output=msvce-libraries" `
    (Get-MsvceVcpkgLibraryList $Libraries) `
    | Write-Verbose


  $librariesDirectory = "$DataDirectory/libraries"
  Write-Verbose "Moving the exported directory to $librariesDirectory"

  if (Test-Path -LiteralPath $librariesDirectory) {
    Remove-Item -Recurse -LiteralPath $librariesDirectory
  }

  Move-Item `
    -Destination $librariesDirectory `
    -LiteralPath "$VcpkgDirectory/msvce-libraries"
}

<#
.SYNOPSIS

Installs the MSVCE configuration file into the directory.

.DESCRIPTION

From the existing data directory and the docker image, figures out all important
information to put in c++.local.properties, and then builds that file into the
data directory.

.PARAMETER DataDirectory

The directory which MSVCE can use as its C:\Data.

.PARAMETER DockerTag

The tag of the msvce image to look in, to see where the SDK is installed.

.PARAMETER CProperties

Generate c.local.properties as opposed to c++.local.properties.

.INPUTS

None
  This cmdlet does not accept any input.

.OUTPUTS

None
  This cmdlet does not generate any output.

.NOTES

This cmdlet is for debug use only. Generally, one should use
Build-MsvceDataDirectory to do everything.

.LINK
Build-MsvceDataDirectory
.LINK
Get-MsvceToolsetVersions
.LINK
Get-MsvceToolsetPrettyName
.LINK
Test-MsvceToolsetExistence
.LINK
Install-MsvceBaseCEFiles
#>
function Install-MsvceConfigurationFile {
  [CmdletBinding(PositionalBinding=$false, DefaultParameterSetName='FindSdk')]
  Param(
    [Parameter(Mandatory=$true, Position=0)]
    [ValidateScript({Test-Path -LiteralPath $_ -PathType 'Container'})]
    [string]$DataDirectory,

    [Parameter(Mandatory=$true, ParameterSetName='FindSdk')]
    [string]$DockerTag,

    [Parameter()]
    [switch]$CProperties,

    [Parameter(Mandatory=$false)]
    [array]$VcpkgVersion = (Get-MsvceConfig 'vcpkg/release'),

    [Parameter(Mandatory=$false)]
    [hashtable]$Libraries = (Get-MsvceConfig 'vcpkg/libraries'),

    [Parameter(Mandatory=$false, DontShow, ParameterSetName='SetSdk')]
    [string]$SdkVersion
  )


  if ($CProperties) {
    $compilerIdPrefix = 'c';
    $propertiesFilename = 'c.local.properties'
  } else {
    $compilerIdPrefix = ''
    $propertiesFilename = 'c++.local.properties'
  }


  <#
    we need to generate the c++.local.properties file based on the
    information stored in $DataDirectory -- if something doesn't exist,
    we should fail early rather than build an incorrect c++.local.properties
    file
  #>

  $basePath = "$DataDirectory\compiler-explorer"
  $baseCompilerPath = "$DataDirectory\msvc"
  if (-not (Test-Path -LiteralPath "$baseCompilerPath" -PathType 'Container')) {
    throw "No MSVC installations in $DataDirectory -- did you use the right folder?"
  }

  <#
    then, we'll find the Windows SDK version number
    this is based on the docker image

    yes, this is the right way to find the version number, at least as of
    10.0.18362.0; I hate it, but this is what the SDK team wants you to do.
  #>

  if ([string]::IsNullOrEmpty($SdkVersion)) {
    Write-Verbose "Getting Windows SDK product identity from msvce:$DockerTag"
    [string]$manifest = docker run --rm "msvce:$DockerTag" `
      'cmd' '/S' '/C' 'type' 'C:\WinSdk\SDKManifest.xml'
    $manifestFileList = Select-Xml -Content $manifest -XPath FileList
    if ($null -eq $manifestFileList) {
      Write-Error 'Malformed SDKManifest.xml'
    }
    $sdkIdentity = $manifestFileList.Node.PlatformIdentity

    if (-not ($sdkIdentity -match 'UAP, Version=(.*)')) {
      Write-Error "Malformed PlatformIdentity: $sdkIdentity"
    }
    $SdkVersion = $Matches[1]
  }
  Write-Verbose "Found SDK version: $SdkVersion"

  # Now we're going to find the compiler versions.

  Write-Verbose 'Finding installed compiler versions'

  $compilerVersions = `
    Get-ChildItem -LiteralPath "$DataDirectory\msvc" -Name | Sort-Object
  Write-Verbose "Compiler versions found:`n$($compilerVersions -join "`n")"

  # Let's check if there are any vcpkg libraries
  $librariesExist = Test-Path -LiteralPath "$DataDirectory\libraries"
  if (-not $librariesExist) {
    Write-Warning "No vcpkg libraries found"
  }

  # Now to build the actual configuration file!

  if (-not (Test-Path -LiteralPath $basePath)) {
    New-Item -Path $basePath -ItemType 'Directory' | Out-Null
  }

  $outputFile = "$basePath\$propertiesFilename"

  function IncludesForArch {
    param([string]$Arch)

    [string[]] $includeDirectories =
      @('cppwinrt', 'shared', 'ucrt', 'um', 'winrt') `
      | ForEach-Object {
        "C:/WinSdk/Include/$SdkVersion/$_"
      }

    if ($librariesExist) {
      $archName = Get-MsvceConfig "vcpkg/architectures/$arch"
      $includeDirectories += "C:/data/libraries/installed/$archName/include"
    }

    return $includeDirectories -join ';'
  }

  function GetLastStableVersion {
    Param([string[]] $Versions)
    $stableVersions = $Versions | Where-Object { -not (Get-MsvceToolsetPrettyName $_).Contains('latest') }
    $stableVersions[-1]
  }

  if ($compilerVersions -is [array]) {
    $demanglerVersion = GetLastStableVersion $compilerVersions
  } else {
    $demanglerVersion = $compilerVersions
  }

  [string[]] $file = @()

  if (-not $CProperties) {
    $file += "demangler=C:/data/msvc/$demanglerVersion/bin/Hostx64/x64/undname.exe"
  } else {
    $file += "demangler="
  }

  $file += "supportsBinary=false"
  $file += "compilers=&${compilerIdPrefix}vcpp_x86:&${compilerIdPrefix}vcpp_x64"
  $file += ""

  function InternalName {
    Param([string]$Arch, [string]$Version)
    $prettyName = (Get-MsvceToolsetPrettyName $Version) -replace '[. ]','_'
    return "${compilerIdPrefix}vcpp_${prettyName}_$Arch"
  }

  function ArchOptions {
    Param([string]$Arch)
    $internalNames = $compilerVersions | ForEach-Object {
      InternalName $Arch $_
    }
    return @(
      "group.${compilerIdPrefix}vcpp_$Arch.options=-EHsc",
      "group.${compilerIdPrefix}vcpp_$Arch.compilerType=win32-vc",
      "group.${compilerIdPrefix}vcpp_$Arch.needsMulti=false",
      "group.${compilerIdPrefix}vcpp_$Arch.includeFlag=/I",
      "group.${compilerIdPrefix}vcpp_$Arch.versionFlag=/?",
      "group.${compilerIdPrefix}vcpp_$Arch.versionRe=^.*Microsoft \(R\).*$",
      "group.${compilerIdPrefix}vcpp_$Arch.compilers=$($internalNames -join ':')",
      "group.${compilerIdPrefix}vcpp_$Arch.groupName=MSVC $Arch",
      "group.${compilerIdPrefix}vcpp_$Arch.isSemVer=true",
      '')
  }

  $file += ArchOptions 'x86'
  $file += ArchOptions 'x64'

  function CompilerOptions {
    Param([string]$Arch, [string]$Version)

    $internalName = InternalName $Arch $Version
    $toolset = Get-MsvceToolset $Version
    $prettyName = $toolset.pretty
    $path = "C:/data/msvc/$Version"

    $includes = "$path/include;$(IncludesForArch $Arch)"

    $ret = @(
      "compiler.$internalName.exe=$path/bin/Host$Arch/$Arch/cl.exe",
      "compiler.$internalName.includePath=$includes",
      "compiler.$internalName.name=$Arch msvc $prettyName",
      "compiler.$internalName.semver=$Version")

    if ($toolset.Contains('legacy_aliases') -and $toolset.legacy_aliases.Contains($Arch)) {
      $ret += $toolset.legacy_aliases.$Arch | ForEach-Object {
        "compiler.$internalName.alias=$_"
      }
    }

    return $ret
  }

  $compilerVersions | ForEach-Object {
    $file += CompilerOptions 'x86' $_
    $file += CompilerOptions 'x64' $_
  }

  $libraryNames = $Libraries.GetEnumerator() | ForEach-Object {
    if ($null -eq $_.Value) {
      return
    }

    $_.Name -replace '-','_'
  }

  if (-not $CProperties) {
    $file += ('libs=' + ($libraryNames -join ':'))

    $Libraries.GetEnumerator() | ForEach-Object {
      if ($null -eq $_.Value) {
        return
      }

      $ceName = $_.Name -replace '-','_'
      [string[]] $libraryDescription = @(
        "libs.${ceName}.name=$($_.Value.pretty_name)",
        "libs.${ceName}.versions=vcpkg",
        "libs.${ceName}.versions.vcpkg.version=vcpkg ${VcpkgVersion}",
        "libs.${ceName}.url=$($_.Value.url)",
        # note: we can add these paths later
        "libs.${ceName}.versions.vcpkg.path="
      )

      if ($_.Value.ContainsKey('description')) {
        $libraryDescription += "libs.${ceName}.description=$($_.Value.description)"
      }

      $file += $libraryDescription
    }
  }

  return New-Item `
    -Path $outputFile `
    -Value ($file -join "`n") `
    -Force
}

<#
.SYNOPSIS

Installs the base MSVCE files into the data directory.

.DESCRIPTION

Copies three files into the data directory:
  - $CEProperties -> $basePath\cookies.html
  - $PrivacyPolicy -> $basePath\privacy.html
  - $CookiePolicy -> $basePath\compiler-explorer.local.properties
where $basePath = "$DataDirectory\compiler-explorer"

By default, these files are loaded from the script root.

.PARAMETER DataDirectory

The directory which MSVCE can use as its C:\data.

.PARAMETER CookiePolicy

The cookie policy html file.
Defaults to cookie_policy.html in the script root.

.PARAMETER PrivacyPolicy

The privacy policy html file.
Defaults to privacy_policy.html in the script root.

.PARAMETER CEProperties

The compiler-explorer.local.properties file.
Defaults to compiler-explorer.properties in the script root.

.INPUTS

None
  This cmdlet does not accept any input.

.OUTPUTS

None
  This cmdlet does not generate any output.

.NOTES

This cmdlet is for debug use only. Generally, one should use
Build-MsvceDataDirectory to do everything.

.LINK
Build-MsvceDataDirectory
.LINK
Get-MsvceToolsetVersions
.LINK
Get-MsvceToolsetPrettyName
.LINK
Test-MsvceToolsetExistence
.LINK
Install-MsvceConfigurationFile
#>
function Install-MsvceBaseCEFiles {
  [CmdletBinding(PositionalBinding=$false)]
  Param(
    [Parameter(Mandatory=$true, Position=0)]
    [ValidateScript({Test-Path -LiteralPath $_ -PathType 'Container'})]
    [string]$DataDirectory,

    [Parameter(Mandatory=$false)]
    [ValidateScript({Test-Path -LiteralPath $_ -PathType 'Leaf'})]
    [string]$CookiePolicy = "$PSScriptRoot\files\cookie_policy.html",

    [Parameter(Mandatory=$false)]
    [ValidateScript({Test-Path -LiteralPath $_ -PathType 'Leaf'})]
    [string]$PrivacyPolicy = "$PSScriptRoot\files\privacy_policy.html",

    [Parameter(Mandatory=$false)]
    [ValidateScript({Test-Path -LiteralPath $_ -PathType 'Leaf'})]
    [string]$CEProperties = "$PSScriptRoot\files\compiler-explorer.properties",

    [Parameter(Mandatory=$false)]
    [ValidateScript({Test-Path -LiteralPath $_ -PathType 'Leaf'})]
    [string]$PythonProperties = "$PSScriptRoot\files\python.properties"
  )

  $ErrorActionPreference = 'Stop'

  $basePath = "$DataDirectory\compiler-explorer"
  <#
    The three files we need to copy to are:
      - $basePath\compiler-explorer.local.properties
      - $basePath\privacy.html
      - $basePath\cookies.html
  #>

  if (-not (Test-Path $basePath)) {
    New-Item -Path $basePath -ItemType 'Directory' | Out-Null
  }

  Copy-Item -LiteralPath $CookiePolicy -Destination "$basePath\cookies.html"
  Copy-Item -LiteralPath $PrivacyPolicy -Destination "$basePath\privacy.html"
  Copy-Item `
    -LiteralPath $CEProperties `
    -Destination "$basePath\compiler-explorer.local.properties"
  Copy-Item `
    -LiteralPath $PythonProperties `
    -Destination "$basePath\python.local.properties"
}


<#
.SYNOPSIS

Runs the MSVCE docker instance with all the correct flags

.DESCRIPTION

Calls 'docker run' to run the specified tag of the 'msvce' docker image. Allows
for interactive use with the '-Interactive' argument, or detached otherwise. By
default, runs the command included in the docker image, which is usually
Compiler Explorer.

If in detached mode, Start-MsvceDockerContainer passes the '--rm' flag to
'docker run'. When the container is stopped, this will cause the container to be
removed.

.PARAMETER DataDirectory

The directory in which data is stored; linked to C:\data in the container.

.PARAMETER DockerTag

The docker tag of 'msvce' to use. Defaults to 'test', as in 'msvce:test'.

.PARAMETER Port

The port that MSVCE should connect to on the host machine. Defaults to 10240.

.PARAMETER Interactive

If this switch is passed, then the docker container will run in interactive
mode.

.PARAMETER Command

The command to run in the container. If nothing is passed, then the command from
the image is run.

.INPUTS

None
  This cmdlet does not accept any input.

.OUTPUTS

System.String
  The container ID of the started container.

.NOTES

This cmdlet is only for local testing only.

.LINK
Build-MsvceDockerImage
.LINK
Build-MsvceDataDirectory
#>
function Start-MsvceDockerContainer {
  [CmdletBinding(PositionalBinding=$false)]
  Param(
    [Parameter(Mandatory=$true)]
    [string]$DataDirectory,

    [Parameter(Mandatory=$false)]
    [string]$DockerImage = 'msvce',

    [Parameter(Mandatory=$false)]
    [string]$DockerTag = 'test',

    [Parameter(Mandatory=$false)]
    [int]$Port = 10240,

    [Parameter(Mandatory=$false)]
    [switch]$Interactive,

    [Parameter(Mandatory=$false, ValueFromRemainingArguments=$true)]
    [string[]]$Command
  )

  $ErrorActionPreference = 'Stop'

  $dataDirectory = Resolve-Path $DataDirectory

  $fullCommand = @(
    'run',
    '--mount',
    "type=bind,source=${dataDirectory},destination=C:\data",
    '--publish',
    "${Port}:80")

  if ($Interactive) {
    $fullCommand += @('--interactive', '--tty', '--rm')
  } else {
    $fullCommand += '--detach'
  }
  $fullCommand += "${DockerImage}:${DockerTag}"
  if ($null -ne $Command) {
    $fullCommand += $Command
  }

  Write-Verbose "Running docker $($fullCommand -join ' ')"
  return docker @fullCommand
}


# TODO: expand comments
Export-ModuleMember -Function 'Get-MsvceConfig'

Export-ModuleMember -Function @(
  'Build-MsvceDockerImage',

  'Build-Template',
  'Get-MsvceCompilerExplorer',
  'Get-MsvceNode',
  'Get-MsvceWindowsSdk')

Export-ModuleMember -Function @(
  'Build-MsvceDataDirectory',

  'Get-MsvceToolsetVersions',
  'Get-MsvceToolsetPrettyName',
  'Install-MsvceBaseCEFiles',
  'Test-MsvceToolsetExistence',
  'Initialize-MsvceVcpkg',
  'Get-MsvceVcpkgLibraryList',
  'Build-MsvceVcpkgLibraries',
  'Install-MsvceVcpkgLibraries',
  'Install-MsvceConfigurationFile')

Export-ModuleMember -Function 'Start-MsvceDockerContainer'
