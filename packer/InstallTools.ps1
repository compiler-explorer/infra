New-Item /tmp -ItemType Directory -Force
Set-Location -Path /tmp

$nginx_path = "/nginx"

function InstallAwsTools {
    Write-Host "Downloading AWS cli"
    Invoke-WebRequest -Uri "https://awscli.amazonaws.com/AWSCLIV2.msi" -OutFile "C:\tmp\awscli.msi"
    Write-Host "Installing AWS cli"
    Start-Process "msiexec" -argumentlist "/quiet ALLUSERS=1 /i awscli.msi" -wait
    Write-Host "Deleting tmp files"
    Remove-Item -Force "awscli.msi"
}

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
    Invoke-WebRequest -Uri "https://nodejs.org/download/release/v18.14.2/node-v18.14.2-x64.msi" -OutFile "C:\tmp\node-installer.msi"
    Write-Host "Installing Node"
    Start-Process "msiexec" -argumentlist "/quiet ALLUSERS=1 /i node-installer.msi" -wait
    Write-Host "Deleting tmp files"
    Remove-Item -Force "node-installer.msi"
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

function InstallNssm {
    Write-Host "Downloading nssm"
    Invoke-WebRequest -Uri "https://nssm.cc/ci/nssm-2.24-103-gdee49fc.zip" -OutFile "/tmp/nssm.zip"
    Write-Host "Installing nssm"
    Expand-Archive -Path "/tmp/nssm.zip" -DestinationPath "/tmp"
    Move-Item -Path "/tmp/nssm-2.24-103-gdee49fc" -Destination "/nssm"
    Remove-Item -Force -Path "/tmp/nssm.zip"
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

function InstallAsService {
    param(
        [string] $Name,
        [string] $Exe,
        [array] $Arguments,
        [string] $WorkingDirectory,
        [bool] $NetUser
    )

    $tmplog = "C:/tmp/log"
    Write-Host "nssm.exe install $Name $Exe"
    /nssm/win64/nssm.exe install $Name $Exe
    if ($Arguments.Length -gt 0) {
        Write-Host "nssm.exe set $Name AppParameters" ($Arguments -join " ")
        /nssm/win64/nssm.exe set $Name AppParameters ($Arguments -join " ")
    }
    Write-Host "nssm.exe set $Name AppDirectory $WorkingDirectory"
    /nssm/win64/nssm.exe set $Name AppDirectory $WorkingDirectory
    Write-Host "nssm.exe set $Name AppStdout $tmplog/$Name-svc.log"
    /nssm/win64/nssm.exe set $Name AppStdout "$tmplog/$Name-svc.log"
    Write-Host "nssm.exe set $Name AppStderr $tmplog/$Name-svc.log"
    /nssm/win64/nssm.exe set $Name AppStderr "$tmplog/$Name-svc.log"
    if ($NetUser) {
        Write-Host "nssm.exe set $Name ObjectName NT AUTHORITY\NetworkService"
        /nssm/win64/nssm.exe set $Name ObjectName "NT AUTHORITY\NetworkService" ""
    }
    Write-Host "nssm.exe set $Name AppExit Default Exit"
    /nssm/win64/nssm.exe set $Name AppExit Default Exit
}

function ConfigureNginx {
    Invoke-WebRequest -Uri "https://raw.githubusercontent.com/compiler-explorer/infra/main/nginx/nginx-win.conf" -OutFile "/tmp/nginx-win.conf"
    Copy-Item -Path "/tmp/nginx-win.conf" -Destination "$nginx_path/conf/nginx.conf" -Force

    InstallAsService -Name "nginx" -Exe "$nginx_path/nginx.exe" -WorkingDirectory $nginx_path -NetUser $true
}

function InstallAndConfigureNginx {
    InstallNginx

    ConfigureNginx
}

function InstallCEStartup {
    Invoke-WebRequest -Uri "https://raw.githubusercontent.com/compiler-explorer/infra/main/packer/Startup.ps1" -OutFile "C:\tmp\Startup.ps1"

    InstallAsService -Name "cestartup" -Exe "C:\Program Files\PowerShell\7\pwsh.exe" -WorkingDirectory "C:\tmp" -Arguments ("C:\tmp\Startup.ps1") -NetUser $false
}

InstallAwsTools
InstallGIT
InstallNodeJS
InstallGrafana
InstallExporter
InstallNssm
InstallAndConfigureNginx
InstallCEStartup
