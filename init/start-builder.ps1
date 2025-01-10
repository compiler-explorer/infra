do {
  $ping = test-connection -comp "s3.amazonaws.com" -count 1 -Quiet
} until ($ping)

$userdata = Invoke-WebRequest -Uri "http://169.254.169.254/latest/user-data" -UseBasicParsing
$env:CE_ENV = $userdata -as [string]
$CE_ENV = $env:CE_ENV
$env:PATH = "$env:PATH;C:\Program Files\Amazon\AWSCLIV2"

$betterComputerName = "win-builder"

function FetchInfra {
    Set-Location -Path "C:\tmp"
    git clone https://github.com/compiler-explorer/infra

    Set-Location -Path "C:\tmp\infra"
    & ./ce_install.ps1 --help

    $conan_home = conan config home
    Copy-Item -Path "/tmp/infra/init/settings.yml" -Destination "${conan_home}/settings.yml"
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

function ConfigureSmbRights {
    $tmpfile = "c:\tmp\secpol.cfg"
    secedit /export /cfg $tmpfile
    $secpol = (Get-Content $tmpfile)

    $Value = $secpol | Where-Object{ $_ -like "MACHINE\SYSTEM\CurrentControlSet\Services\LanmanWorkstation\Parameters\AllowInsecureGuestAuth" }
    $Index = [array]::IndexOf($secpol,$Value)
    if ($Index -eq -1) {
        $Index = [array]::IndexOf($secpol, "[Registry Values]")
        $idx2 = $Index + 1
        $NewValue = "MACHINE\SYSTEM\CurrentControlSet\Services\LanmanWorkstation\Parameters\AllowInsecureGuestAuth=4,1"
        $newpol = $secpol[0..$Index]
        $newpol += ($NewValue)
        $newpol += $secpol[$idx2..$secpol.Length]
        $secpol = $newpol
    } else {
        $NewValue = "MACHINE\SYSTEM\CurrentControlSet\Services\LanmanWorkstation\Parameters\AllowInsecureGuestAuth=4,1"
        $secpol.item($Index) = $NewValue
    }

    $secpol | out-file $tmpfile -Force
    secedit /configure /db c:\windows\security\local.sdb /cfg $tmpfile
    Remove-Item -Path $tmpfile

    gpupdate /Force
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
    while (-not $exists) {
        try {
            Write-Host "Mapping Z:"
            $exists = (New-SmbMapping -LocalPath "Z:" -RemotePath "\\$smb_ip\winshared") -as [bool]
        } catch {
            Write-Host "New-SmbMapping for Z:\ -> \\$smb_ip\winshared failed: $_"
        }
    }
}

function GetResolvedIPAddress {
    param(
        [string] $Hostname
    )

    $resolved = Resolve-DnsName -Name $hostname
    $first = $resolved[0]
    if (!$first.IPAddress) {
        return (GetResolvedIPAddress $first.NameHost)
    } else {
        return $first.IPAddress
    }
}

function AddToHosts {
    param(
        [string] $Hostname
    )

    $ip = GetResolvedIPAddress $hostname

    $content = Get-Content "C:\Windows\System32\drivers\etc\hosts"
    $content = $content,($ip + " " + $Hostname)
    Set-Content -Path "C:\Windows\System32\drivers\etc\hosts" -Value $content

    return $ip
}

function AddLocalHost {
    $content = Get-Content "C:\Windows\System32\drivers\etc\hosts"
    $content = $content,("127.0.0.1 localhost")
    Set-Content -Path "C:\Windows\System32\drivers\etc\hosts" -Value $content
}

ConfigureSmbRights

MountZ

InitializeAgentConfig

FetchInfra
