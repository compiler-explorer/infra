New-Item /tmp -ItemType Directory -Force
Set-Location -Path /tmp

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
    Write-Host "Downloading nssm"
    Invoke-WebRequest -Uri "https://nssm.cc/ci/nssm-2.24-103-gdee49fc.zip" -OutFile "/tmp/nssm.zip"
    Write-Host "Installing nssm"
    Expand-Archive -Path "/tmp/nssm.zip" -DestinationPath "/tmp"
    Move-Item -Path "/tmp/nssm-2.24-103-gdee49fc" -Destination "/nssm"
    Remove-Item -Force -Path "/tmp/nssm.zip"
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
    Invoke-WebRequest -Uri "https://github.com/Kitware/CMake/releases/download/v3.28.3/cmake-3.28.3-windows-x86_64.zip" -OutFile "/tmp/cmake-win.zip"
    Expand-Archive -Path "/tmp/cmake-win.zip" -DestinationPath "/BuildTools"
    Rename-Item -Path "/BuildTools/cmake-3.28.3-windows-x86_64" -NewName "CMake"
    Remove-Item -Path "/tmp/cmake-win.zip"

    AllowAppContainerRXAccess -Path "C:\BuildTools\CMake"

    Write-Host "Installing Ninja"
    Invoke-WebRequest -Uri "https://github.com/compiler-explorer/ninja/releases/download/v1.12.1/ninja-win.zip" -OutFile "/tmp/ninja-win.zip"
    Expand-Archive -Path "/tmp/ninja-win.zip" -DestinationPath "/BuildTools/Ninja"
    Remove-Item -Path "/tmp/ninja-win.zip"

    AllowAppContainerRXAccess -Path "C:\BuildTools\Ninja"
}


function InstallPython {
    # note: conan 1.59 won't install with Python 3.12 (because of a dependency), so we use the last 3.10 where there's a .exe
    Write-Host "Downloading python"
    $url = "https://www.python.org/ftp/python/3.10.11/python-3.10.11-amd64.exe"
    Invoke-WebRequest -Uri $url -OutFile "/tmp/python-win.exe"
    Write-Host "Installing python"
    Start-Process -FilePath "/tmp/python-win.exe" -ArgumentList ("-quiet", "InstallAllUsers=1", "TargetDir=C:\BuildTools\Python") -NoNewWindow -Wait

    $env:PATH = "C:\BuildTools\Python;C:\BuildTools\Python\Scripts;$env:PATH"
}


function InstallConan {
    Write-Host "Installing conan"
    python -m pip install conan==1.59

    Write-Host "Configuring conan"
    conan remote clean
    conan remote add ceserver https://conan.compiler-explorer.com/ True

    $conan_home = conan config home
    # todo: copy settings.yml from infra to $conan_home
}


InstallAwsTools
InstallGIT
InstallBuildTools
InstallGrafana
InstallExporter
InstallPython
InstallConan
InstallNssm
# InstallCEStartup
# todo: do we install a service to do something at startup? or what?
