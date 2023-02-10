New-Item C:\tmp -ItemType Directory -Force
Set-Location -Path C:\tmp

Write-Host "Downloading GIT"
Invoke-WebRequest -Uri "https://github.com/git-for-windows/git/releases/download/v2.28.0.windows.1/Git-2.28.0-64-bit.exe" -OutFile "C:\tmp\Git-2.28.0-64-bit.exe"
Write-Host "Installing GIT"
Start-Process "Git-2.28.0-64-bit.exe" -argumentlist "/silent /verysilent" -wait
Write-Host "Deleting tmp files"
Remove-Item -Force "Git-2.28.0-64-bit.exe"

Write-Host "Downloading NodeJS"
Invoke-WebRequest -Uri "https://nodejs.org/download/release/v16.19.0/node-v16.19.0-x64.msi" -OutFile "C:\tmp\node-installer.msi"
Write-Host "Installing Node"
Start-Process "msiexec" -argumentlist "/quiet ALLUSERS=1 /i node-installer.msi" -wait
Write-Host "Deleting tmp files"
Remove-Item -Force "node-installer.msi"

Write-Host "Installing AWS tools, might take a while"
pwsh -Command Install-Module -Name AWS.Tools.Common -Force
pwsh -Command Install-Module -Name AWS.Tools.Installer -Force
pwsh -Command Install-AWSToolsModule AWS.Tools.SimpleSystemsManagement -Force
Write-Host "Done installing AWS Tools"

Write-Host "Downloading Grafana agent"
Invoke-WebRequest -Uri "https://github.com/grafana/agent/releases/download/v0.30.2/grafana-agent-installer.exe" -OutFile "C:\tmp\grafana-agent-installer.exe"
Write-Host "Installing Grafana agent"
Start-Process "grafana-agent-installer.exe" -argumentlist "/S" -wait
# Remove-Item -Path "C:\tmp\grafana-agent-installer.exe" # installer is run in the background, so cant delete it yet

Write-Host "Downloading windows-exporter"
Invoke-WebRequest -Uri "https://github.com/prometheus-community/windows_exporter/releases/download/v0.20.0/windows_exporter-0.20.0-amd64.msi" -OutFile "C:\tmp\windows_exporter-0.20.0-amd64.msi"
Write-Host "Installing windows-exporter"
Start-Process "msiexec" -argumentlist "/quiet /i windows_exporter-0.20.0-amd64.msi" -wait
Write-Host "Deleting tmp files"
Remove-Item -Force -Path "windows_exporter-0.20.0-amd64.msi"


# todo populate C:\Program Files\Grafana Agent\agent-config.yaml with things

Invoke-WebRequest -Uri "https://raw.githubusercontent.com/compiler-explorer/infra/main/packer/Startup.ps1" -OutFile "C:\tmp\Startup.ps1"

$TaskParams = @{
    Action = New-ScheduledTaskAction -Execute "pwsh" -Argument "C:\tmp\Startup.ps1"
    Trigger = New-ScheduledTaskTrigger -AtStartup
    Principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount
    Settings = New-ScheduledTaskSettingsSet
}
New-ScheduledTask @TaskParams | Register-ScheduledTask "Startup"
