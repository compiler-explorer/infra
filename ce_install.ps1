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

# Sync dependencies if needed
if (! (Test-Path -Path .venv)) {
    & $uvBin sync --no-install-project
}

& $uvBin run python -c "import sys; sys.path.append(r'$cwd/bin'); from lib.ce_install import main; main()" $args
