# Fail the build on any error instead of silently shipping a half-installed AMI.
$ErrorActionPreference = 'Stop'

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

function InstallVCRedist {
    param(
        [string] $Arch,
        [string] $Url,
        [string] $Sha256
    )

    $installer = "C:\tmp\VC_redist.$Arch.exe"
    Write-Host "Downloading VC++ redistributable ($Arch)"
    Invoke-WebRequest -Uri $Url -OutFile $installer
    $hash = (Get-FileHash -Path $installer -Algorithm SHA256).Hash
    if ($hash -ne $Sha256) { throw "VC_redist.$Arch.exe hash mismatch: $hash" }
    Write-Host "Installing VC++ redistributable ($Arch)"
    $process = Start-Process $installer -ArgumentList "/install /quiet /norestart" -Wait -PassThru
    # 3010: installed, reboot required; 1638: same or newer version already present
    if ($process.ExitCode -notin 0, 3010, 1638) { throw "VC_redist.$Arch.exe failed with exit code $($process.ExitCode)" }
    Remove-Item -Force $installer
}

function InstallVCRedists {
    $base = "https://download.visualstudio.microsoft.com/download/pr/73aabf2e-9532-4f68-99f7-3247081a619c"
    InstallVCRedist -Arch "x64" `
        -Url "$base/CC0FF0EB1DC3F5188AE6300FAEF32BF5BEEBA4BDD6E8E445A9184072096B713B/VC_redist.x64.exe" `
        -Sha256 "CC0FF0EB1DC3F5188AE6300FAEF32BF5BEEBA4BDD6E8E445A9184072096B713B"
    InstallVCRedist -Arch "x86" `
        -Url "$base/0C09F2611660441084CE0DF425C51C11E147E6447963C3690F97E0B25C55ED64/VC_redist.x86.exe" `
        -Sha256 "0C09F2611660441084CE0DF425C51C11E147E6447963C3690F97E0B25C55ED64"
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
    # packer sets NODE_VERSION from the repo-root node-version file (see win.pkr.hcl).
    $nodeVersion = $env:NODE_VERSION
    if (-not $nodeVersion) { throw "NODE_VERSION not set" }
    Write-Host "Downloading NodeJS v$nodeVersion"
    Invoke-WebRequest -Uri "https://nodejs.org/download/release/v$nodeVersion/node-v$nodeVersion-x64.msi" -OutFile "C:\tmp\node-installer.msi"
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
    Start-Process "msiexec" -argumentlist "/quiet /i windows_exporter-0.20.0-amd64.msi ENABLED_COLLECTORS=cpu,cs,logical_disk,net,os,system" -wait
    Write-Host "Deleting tmp files"
    Remove-Item -Force -Path "windows_exporter-0.20.0-amd64.msi"
}

function InstallNssm {
    $url = "https://nssm.cc/ci/nssm-2.24-103-gdee49fc.zip"
    $extracted = "/tmp/nssm-2.24-103-gdee49fc"
    Write-Host "Downloading nssm"
    # nssm.cc is flaky and can serve truncated zips; retry and verify before continuing.
    for ($attempt = 1; $attempt -le 5; $attempt++) {
        try {
            Remove-Item -Recurse -Force "/tmp/nssm.zip", $extracted -ErrorAction SilentlyContinue
            Invoke-WebRequest -Uri $url -OutFile "/tmp/nssm.zip"
            Expand-Archive -Path "/tmp/nssm.zip" -DestinationPath "/tmp" -Force
            if (Test-Path "$extracted/win64/nssm.exe") { break }
            throw "nssm archive missing win64/nssm.exe"
        } catch {
            Write-Host "nssm download attempt $attempt failed: $_"
            if ($attempt -eq 5) { throw "Failed to install nssm after 5 attempts" }
            Start-Sleep -Seconds 5
        }
    }
    Write-Host "Installing nssm"
    Move-Item -Path $extracted -Destination "/nssm"
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

function AllowAppContainerRXAccess {
    param (
        $Path
    )

    $ACL = Get-ACL -Path $Path
    $AccessRule = New-Object System.Security.AccessControl.FileSystemAccessRule("ALL APPLICATION PACKAGES", "ReadAndExecute", "ContainerInherit, ObjectInherit", "None", "Allow")
    $ACL.AddAccessRule($AccessRule)
    $ACL | Set-Acl -Path $Path
}

function InstallBuildTools {
    New-Item -Path "/BuildTools" -ItemType Directory

    Write-Host "Installing CMake"
    Invoke-WebRequest -Uri "https://github.com/Kitware/CMake/releases/download/v4.4.2/cmake-4.4.2-windows-x86_64.zip" -OutFile "/tmp/cmake-win.zip"
    Expand-Archive -Path "/tmp/cmake-win.zip" -DestinationPath "/BuildTools"
    Rename-Item -Path "/BuildTools/cmake-4.4.2-windows-x86_64" -NewName "CMake"
    Remove-Item -Path "/tmp/cmake-win.zip"

    AllowAppContainerRXAccess -Path "C:\BuildTools\CMake"

    Write-Host "Installing Ninja"
    Invoke-WebRequest -Uri "https://github.com/compiler-explorer/ninja/releases/download/v1.12.1/ninja-win.zip" -OutFile "/tmp/ninja-win.zip"
    Expand-Archive -Path "/tmp/ninja-win.zip" -DestinationPath "/BuildTools/Ninja"
    Remove-Item -Path "/tmp/ninja-win.zip"

    AllowAppContainerRXAccess -Path "C:\BuildTools\Ninja"
}

function Disable-WindowsUpdatePermanent {
    Write-Host "Attempting to disable Windows Update..."

    Stop-Service -Name wuauserv -Force -ErrorAction SilentlyContinue
    Set-Service -Name wuauserv -StartupType Manual
}

function Disable-WindowsDefenderPermanent {
    Write-Host "Attempting to disable Windows Defender..."

    $defenderKey = "HKLM:\SOFTWARE\Policies\Microsoft\Windows Defender"
    if (-not (Test-Path $defenderKey)) {
        New-Item -Path $defenderKey -Force | Out-Null
    }
    Set-ItemProperty -Path $defenderKey -Name "DisableAntiSpyware" -Value 1
}

function Disable-VisualStudioTelemetry {
    Write-Host "Opting out of Visual Studio telemetry..."

    $sqmKey = "HKLM:\SOFTWARE\Policies\Microsoft\VisualStudio\SQM"
    if (-not (Test-Path $sqmKey)) {
        New-Item -Path $sqmKey -Force | Out-Null
    }
    Set-ItemProperty -Path $sqmKey -Name "OptIn" -Value 0 -Type DWord
}

function InstallWinFsp {
    Invoke-WebRequest -Uri "https://github.com/winfsp/winfsp/releases/download/v2.0/winfsp-2.0.23075.msi" -OutFile "C:\tmp\winfsp.msi"
    Start-Process "msiexec" -argumentlist "/i winfsp.msi /quiet ALLUSERS=1" -wait
}

function InstallOpenSSH {
    # Not Add-WindowsCapability: DISM wants a fully elevated token, which the packer WinRM
    # session does not have, and it fails with "Access is denied".
    $version = "10.0.0.0p2-Preview"
    Write-Host "Downloading OpenSSH $version"
    Invoke-WebRequest -Uri "https://github.com/PowerShell/Win32-OpenSSH/releases/download/$version/OpenSSH-Win64.zip" -OutFile "/tmp/openssh.zip"
    Expand-Archive -Path "/tmp/openssh.zip" -DestinationPath "/tmp/openssh" -Force
    Move-Item -Path "/tmp/openssh/OpenSSH-Win64" -Destination "C:\Program Files\OpenSSH"
    Remove-Item -Force -Recurse -Path "/tmp/openssh.zip", "/tmp/openssh"

    Write-Host "Installing sshd"
    & powershell.exe -ExecutionPolicy Bypass -File "C:\Program Files\OpenSSH\install-sshd.ps1"

    # install-sshd.ps1 registers the service as Manual and does not start it, which is what we
    # want: init/start.ps1 installs the authorized keys and generates per-instance host keys
    # before starting it, so no host identity ends up shared across the fleet via the AMI.
    Set-Service -Name sshd -StartupType Manual

    # Remote commands arrive as `<DefaultShell> <DefaultShellCommandOption> <command>`.
    # Without this they run under cmd.exe, which mangles anything quoted for a POSIX shell.
    # sftp is unaffected -- it goes via the subsystem, not the login shell.
    New-Item -Path "HKLM:\SOFTWARE\OpenSSH" -Force | Out-Null
    New-ItemProperty -Path "HKLM:\SOFTWARE\OpenSSH" -Name DefaultShell `
        -Value "C:\Program Files\PowerShell\7\pwsh.exe" -PropertyType String -Force | Out-Null
    New-ItemProperty -Path "HKLM:\SOFTWARE\OpenSSH" -Name DefaultShellCommandOption `
        -Value "-Command" -PropertyType String -Force | Out-Null
}

InstallWinFsp

Disable-WindowsUpdatePermanent
Disable-WindowsDefenderPermanent
Disable-VisualStudioTelemetry

InstallOpenSSH
InstallAwsTools
InstallVCRedists
InstallGIT
InstallBuildTools
InstallNodeJS
InstallGrafana
InstallExporter
InstallNssm
InstallAndConfigureNginx
InstallCEStartup
