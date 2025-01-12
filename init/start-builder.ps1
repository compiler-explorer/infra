do {
  $ping = test-connection -comp "s3.amazonaws.com" -count 1 -Quiet
} until ($ping)

$userdata = Invoke-WebRequest -Uri "http://169.254.169.254/latest/user-data" -UseBasicParsing
$env:CE_ENV = $userdata -as [string]
$CE_ENV = $env:CE_ENV
$env:PATH = "$env:PATH;C:\BuildTools\Python;C:\BuildTools\Python\Scripts;C:\BuildTools\Ninja;Z:\compilers\windows-kits-10\bin;C:\BuildTools\CMake\bin;Z:\compilers\mingw-w64-13.1.0-16.0.2-11.0.0-ucrt-r1\bin;C:\Program Files\Amazon\AWSCLIV2"

$betterComputerName = "win-builder"

[Environment]::SetEnvironmentVariable("PYTHON_KEYRING_BACKEND", 'keyring.backends.null.Keyring', [System.EnvironmentVariableTarget]::Process);

function FetchInfra {
    Set-Location -Path "C:\tmp"

    $infra = "C:\tmp\infra"
    if (Test-Path -Path $infra) {
        Set-Location -Path "C:\tmp\infra"

        Remove-Item -Path ".env" -Recurse
        Remove-Item -Path ".venv" -Recurse
        Remove-Item -Path ".poetry" -Recurse
        Remove-Item -Path ".mypy_cache" -Recurse

        git reset --hard
        git pull
    } else {
        git clone https://github.com/compiler-explorer/infra
    }

    Set-Location -Path "C:\tmp\infra"
    & ./ce_install.ps1 --help

    $conan_home = conan config home
    Copy-Item -Path "/tmp/infra/init/settings.yml" -Destination "${conan_home}/settings.yml"

    conan remote clean
    conan remote add ceserver https://conan.compiler-explorer.com/ True

    # todo: set conan username and password
}

function GetConf {
    Param(
        $Name,
        $Default = ""
    )

    try {
        return (aws ssm get-parameter --name "$Name" | ConvertFrom-Json).Parameter.Value
    }
    catch {
        Write-Host "GetConf($Name) raised Exception: $_"
        return $Default
    }
}

function InitializeAgentConfig {
    Write-Host "Setting up Grafana Agent"
    $config = Get-Content -Path "/tmp/infra/grafana/agent-win.yaml"
    $config = $config.Replace("@HOSTNAME@", $betterComputerName)
    $config = $config.Replace("@ENV@", $CE_ENV)
    $prom_pass = ""
    try {
        $prom_pass = GetConf -Name "/compiler-explorer/promPassword"
    } catch {
    }
    $config = $config.Replace("@PROM_PASSWORD@", $prom_pass)
    Set-Content -Path "C:\Program Files\Grafana Agent\agent-config.yaml" -Value $config

    Stop-Service "Grafana Agent"
    $started = (Start-Service "Grafana Agent") -as [bool]
    if (-not $started) {
        Start-Service "Grafana Agent"
    }
}

function GetSMBServerIP {
    Param(
        [string] $CeEnv
    )

    $configPath = "/compiler-explorer/smbserverProd"
    $smbserver = GetConf -Name $configPath -Default "smb-address-unknown";

    return $smbserver
}

function MountZ {
    $smb_ip = GetSMBServerIP -CeEnv "prod"
    $exists = Test-Path -Path "Z:\"
    while (-not $exists) {
        try {
            Write-Host "Mapping Z:"
            $exists = (New-SmbMapping -LocalPath "Z:" -RemotePath "\\$smb_ip\winshared") -as [bool]
        } catch {
            Write-Host "New-SmbMapping for Z:\ -> \\$smb_ip\winshared failed: $_"
        }
    }
}

MountZ

FetchInfra

# InitializeAgentConfig
