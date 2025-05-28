# Make sure your python is in PATH, otherwise do something like below before running this script
# $env:PATH = "$env:PATH;E:\Python\Python311"

$cwd = Get-Location

# Check if uv is available system-wide, otherwise install locally
$uvPath = Get-Command uv -ErrorAction SilentlyContinue
if ($uvPath) {
    $uvBin = "uv"
} else {
    $uvBin = "$cwd/.uv/uv.exe"
    if (! (Test-Path -Path $uvBin)) {
        Write-Host "Installing uv..."
        $uvInstallDir = "$cwd/.uv"
        if (! (Test-Path -Path $uvInstallDir)) {
            New-Item -ItemType Directory -Path $uvInstallDir | Out-Null
        }
        # Download and extract uv for Windows
        $uvUrl = "https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip"
        $uvZip = "$uvInstallDir/uv.zip"
        Invoke-WebRequest -Uri $uvUrl -OutFile $uvZip
        Expand-Archive -Path $uvZip -DestinationPath $uvInstallDir -Force
        Remove-Item $uvZip
    }
}

# Sync dependencies
& $uvBin sync --no-install-project

& $uvBin run pre-commit install

& $uvBin run pre-commit run --all-files
