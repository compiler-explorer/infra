New-Item C:\tmp -ItemType Directory -Force
Set-Location -Path C:\tmp

Write-Host "Downloading Pwsh"
Invoke-WebRequest -Uri "https://github.com/PowerShell/PowerShell/releases/download/v7.3.2/PowerShell-7.3.2-win-x64.msi" -Outfile "C:\tmp\PowerShell-7.3.2-win-x64.msi"
Write-Host "Installing Pwsh"
Start-Process "msiexec" -argumentlist "/quiet /i PowerShell-7.3.2-win-x64.msi" -wait
Write-Host "Removing tmp files"
Remove-Item -Force "PowerShell-7.3.2-win-x64.msi"
