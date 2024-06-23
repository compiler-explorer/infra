param (
    [Parameter(Mandatory = $true)][string]$url
)
$ErrorActionPreference = "Stop"

#### WILL COM
$url = "https://aka.ms/vs/17/pre/vs_BuildTools.exe"

$download_path = "%TMP%\download"
$full_install_root = "%TMP%\full"
$archives = "%TMP%\archives"

function Download
{
    Param (
        [string] $version,
        [string] $url
    )

    $versionPath = "$download_path/$version"
    $filepath = "$versionPath/installer.exe"

    if (!(Test-Path -Path $filepath))
    {
        New-Item -ItemType Directory $versionPath
        Invoke-WebRequest -Uri $url -OutFile $filepath
    }
}

function Install
{
    $installer = "$download_path/installer.exe"

    New-Item -ItemType Directory -Force "$full_install_root/$version"
    Start-Process -Wait -FilePath "$installer" -ArgumentList @("--quiet", "--installPath", "$full_install_root", "--add", "Microsoft.VisualStudio.Component.VC.Tools.x86.x64", "--add", "Microsoft.VisualStudio.Component.VC.Tools.ARM64", "--add", "Microsoft.VisualStudio.Component.VC.Tools.ARM")
}

function ZipVC
{
    Param (
        [string] $compilerVersion,
        [string] $productVersion
    )

    New-Item -ItemType Directory -Force "$archives"
    & "7z.exe" a "$archives/$compilerVersion-$productVersion.zip" "$full_install_root/VC/Tools/MSVC/$compilerVersion"
}

New-Item -ItemType Directory -Force "$full_install_root"

Download -url $url
Install

$dir = "$full_install_root/VC/Tools/MSVC"
Get-ChildItem $dir | Foreach-Object {
    $compilerVersion = $_.Name
    Write-Host "Compiler directory version: $compilerVersion"

    $compilerExeProductVersion = (Get-Item "$dir/$compilerVersion/bin/Hostx64/x64/cl.exe").VersionInfo.ProductVersionRaw
    Write-Host "Compiler exe version: $compilerExeProductVersion"

    ZipVC -compilerVersion $compilerVersion -productVersion $compilerExeProductVersion
}
