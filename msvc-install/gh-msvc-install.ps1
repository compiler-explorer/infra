param (
    [Parameter(Mandatory = $true)][string]$url
)
$ErrorActionPreference = "Stop"

# This script is very destructive and is designed to only be run on a GH action runner.
$download_path = "download"
$full_install_root = "full"
$archives = "archives"

function Download
{
    Param (
        [string] $url
    )

    $filepath = "$download_path/installer.exe"

    if (!(Test-Path -Path $filepath))
    {
        New-Item -ItemType Directory $download_path
        Invoke-WebRequest -Uri $url -OutFile $filepath
    }
}

function Install
{
    $installer = "$download_path/installer.exe"

    New-Item -ItemType Directory -Force "$full_install_root"
#    Start-Process -Wait -FilePath "$installer" -ArgumentList @("--quiet", "--installPath", "$full_install_root", "--add", "Microsoft.VisualStudio.Component.VC.Tools.x86.x64", "--add", "Microsoft.VisualStudio.Component.VC.Tools.ARM64", "--add", "Microsoft.VisualStudio.Component.VC.Tools.ARM")
    Start-Process -Wait -FilePath "$installer" -ArgumentList @("--installPath", "$full_install_root", "--add", "Microsoft.VisualStudio.Component.VC.Tools.x86.x64", "--add", "Microsoft.VisualStudio.Component.VC.Tools.ARM64", "--add", "Microsoft.VisualStudio.Component.VC.Tools.ARM")
    Write-Host "Looking in : $full_install_root"
    Get-ChildItem -Path "$full_install_root" -Recurse
    Write-Host "Looked in : $full_install_root"
}

function ZipVC
{
    Param (
        [string] $compilerVersion,
        [string] $productVersion
    )

    New-Item -ItemType Directory -Force "$archives"
    Rename-Item -Path "$full_install_root/VC/Tools/MSVC/$compilerVersion" -NewName "$compilerVersion-$productVersion"
    & "7z.exe" a "$archives/$compilerVersion-$productVersion.zip" "$full_install_root/VC/Tools/MSVC/$compilerVersion-$productVersion"
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
