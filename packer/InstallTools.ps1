New-Item C:\tmp -ItemType Directory -Force
Set-Location -Path C:\tmp

$nginx_path = "/nginx"

function InstallGIT {
    Write-Host "Downloading GIT"
    Invoke-WebRequest -Uri "https://github.com/git-for-windows/git/releases/download/v2.28.0.windows.1/Git-2.28.0-64-bit.exe" -OutFile "C:\tmp\Git-2.28.0-64-bit.exe"
    Write-Host "Installing GIT"
    Start-Process "Git-2.28.0-64-bit.exe" -argumentlist "/silent /verysilent" -wait
    Write-Host "Deleting tmp files"
    Remove-Item -Force "Git-2.28.0-64-bit.exe"
}

function InstallNodeJS {
    Write-Host "Downloading NodeJS"
    Invoke-WebRequest -Uri "https://nodejs.org/download/release/v16.19.0/node-v16.19.0-x64.msi" -OutFile "C:\tmp\node-installer.msi"
    Write-Host "Installing Node"
    Start-Process "msiexec" -argumentlist "/quiet ALLUSERS=1 /i node-installer.msi" -wait
    Write-Host "Deleting tmp files"
    Remove-Item -Force "node-installer.msi"
}

function InstallAwsTools {
    Write-Host "Installing AWS tools, might take a while"
    Start-Sleep -Seconds 1
    pwsh -Command Install-Module -Name AWS.Tools.Common -Force
    Start-Sleep -Seconds 5
    pwsh -Command Install-Module -Name AWS.Tools.Installer -Force
    Start-Sleep -Seconds 5
    pwsh -Command Install-AWSToolsModule AWS.Tools.SimpleSystemsManagement -Force
    Write-Host "Done installing AWS Tools"
}

function InstallGrafana {
    Write-Host "Downloading Grafana agent"
    Invoke-WebRequest -Uri "https://github.com/grafana/agent/releases/download/v0.30.2/grafana-agent-installer.exe" -OutFile "C:\tmp\grafana-agent-installer.exe"
    Write-Host "Installing Grafana agent"
    Start-Process "grafana-agent-installer.exe" -argumentlist "/S" -wait
    Remove-Item -Path "C:\tmp\grafana-agent-installer.exe"
}

function InstallExporter {
    Write-Host "Downloading windows-exporter"
    Invoke-WebRequest -Uri "https://github.com/prometheus-community/windows_exporter/releases/download/v0.20.0/windows_exporter-0.20.0-amd64.msi" -OutFile "C:\tmp\windows_exporter-0.20.0-amd64.msi"
    Write-Host "Installing windows-exporter"
    Start-Process "msiexec" -argumentlist "/quiet /i windows_exporter-0.20.0-amd64.msi" -wait
    Write-Host "Deleting tmp files"
    Remove-Item -Force -Path "windows_exporter-0.20.0-amd64.msi"
}

function InstallNginx {
    # should be moved to ../packer/InstallTools.ps1
    Write-Host "Downloading nginx"
    Invoke-WebRequest -Uri "https://nginx.org/download/nginx-1.23.3.zip" -OutFile "/tmp/nginx.zip"
    Write-Host "Installing nginx"

    # Remove-Item -Path $nginx_path -Force -Recurse
    Expand-Archive -Path "/tmp/nginx.zip" -DestinationPath "/tmp"
    Move-Item -Path "/tmp/nginx-1.23.3" -Destination $nginx_path

    Write-Host "Deleting tmp files"
    Remove-Item -Force "/tmp/nginx.zip"

    New-Item -Path "/tmp/log/nginx" -Force -ItemType Directory
}

function ConfigureNginx {
    Invoke-WebRequest -Uri "https://raw.githubusercontent.com/compiler-explorer/infra/main/nginx/nginx-win.conf" -OutFile "C:\tmp\nginx-win.conf"
    Copy-Item -Path "/tmp/nginx-win.conf" -Destination "$nginx_path/conf/nginx.conf" -Force

    $Settings = New-ScheduledTaskSettingsSet -DontStopOnIdleEnd
    $Settings.ExecutionTimeLimit = "PT0S"

    $TaskParams = @{
        Action = New-ScheduledTaskAction -Execute "$nginx_path/nginx.exe" -WorkingDirectory $nginx_path
        Trigger = New-ScheduledTaskTrigger -AtStartup
        Principal = New-ScheduledTaskPrincipal -UserId "NT AUTHORITY\NetworkService" -LogonType ServiceAccount
        Settings = $Settings
    }
    New-ScheduledTask @TaskParams | Register-ScheduledTask "nginx"
}

function InstallAndConfigureNginx {
    InstallNginx

    ConfigureNginx
}

function InstallCEStartup {
    Invoke-WebRequest -Uri "https://raw.githubusercontent.com/compiler-explorer/infra/main/packer/Startup.ps1" -OutFile "C:\tmp\Startup.ps1"

    $Settings = New-ScheduledTaskSettingsSet -DontStopOnIdleEnd
    $Settings.ExecutionTimeLimit = "PT0S"

    $TaskParams = @{
        Action = New-ScheduledTaskAction -Execute "pwsh" -Argument "C:\tmp\Startup.ps1"
        Trigger = New-ScheduledTaskTrigger -AtStartup
        Principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount
        Settings = $Settings
    }
    New-ScheduledTask @TaskParams | Register-ScheduledTask "Startup"
}

InstallGIT
InstallNodeJS
InstallAwsTools
InstallGrafana
InstallExporter
InstallAndConfigureNginx
InstallCEStartup
