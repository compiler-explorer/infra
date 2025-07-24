New-Item C:\tmp -ItemType Directory -Force
Set-Location -Path C:\tmp

Write-Host "Downloading Pwsh"
Invoke-WebRequest -Uri "https://github.com/PowerShell/PowerShell/releases/download/v7.3.2/PowerShell-7.3.2-win-x64.msi" -Outfile "C:\tmp\PowerShell-7.3.2-win-x64.msi"
Write-Host "Installing Pwsh"
Start-Process "msiexec" -argumentlist "/quiet /i PowerShell-7.3.2-win-x64.msi" -wait
Write-Host "Removing tmp files"
Remove-Item -Force "PowerShell-7.3.2-win-x64.msi"

if (Test-Path -Path "C:\Program Files\PowerShell\7\pwsh.exe") {
    Write-Host "Pwsh installed successfully"
} else {
    throw "Pwsh installation failed"
}
