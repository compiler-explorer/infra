do {
  $ping = test-connection -comp "s3.amazonaws.com" -count 1 -Quiet
} until ($ping)

$userdata = Invoke-WebRequest -Uri "http://169.254.169.254/latest/user-data" -UseBasicParsing
$env:CE_ENV = $userdata -as [string]
$DEPLOY_DIR = "/compilerexplorer"
$CE_ENV = $env:CE_ENV
$CE_USER = "ce"
$env:PATH = "$env:PATH;C:\Program Files\Amazon\AWSCLIV2"
$loghost = "todo"
$logport = "80"

function GetBetterHostname {
    $meta = Invoke-WebRequest -Uri "http://169.254.169.254/latest/meta-data/hostname" -UseBasicParsing
    return $meta -as [string] -replace ".ec2.internal",""
}

$betterComputerName = GetBetterHostname
Write-Host "AWS Hostname $betterComputerName"

function update_code {
    Write-Host "Current environment $CE_ENV"
    Invoke-WebRequest -Uri "https://s3.amazonaws.com/compiler-explorer/version/$CE_ENV" -OutFile "/tmp/s3key.txt"

    $S3_KEY = Get-Content -Path "/tmp/s3key.txt"

    # should not be needed, but just in case we copy pasted the file
    $S3_KEY = $S3_KEY -replace ".tar.xz","zip"

    get_released_code -URL "https://s3.amazonaws.com/compiler-explorer/$S3_KEY"
}

function get_released_code {
    param (
        $URL
    )

    Write-Host "Download build from: $URL"
    Invoke-WebRequest -Uri $URL -OutFile "/tmp/build.zip"

    Write-Host "Unzipping"
    Remove-Item -Path "/compilerexplorer" -Force -Recurse
    New-Item -Path "./" -Name "compilerexplorer" -ItemType "directory" -Force
    Expand-Archive -Path "/tmp/build.zip" -DestinationPath $DEPLOY_DIR
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

function GetLogHost {
    return GetConf -Name "/compiler-explorer/logDestHost";
}

function GetLogPort {
    return GetConf -Name "/compiler-explorer/logDestPort";
}

function DenyAccessByCE {
    param (
        $Path
    )

    $ACL = Get-ACL -Path $Path
    $AccessRule = New-Object System.Security.AccessControl.FileSystemAccessRule("ce", "FullControl", "Deny")
    $ACL.AddAccessRule($AccessRule)
    $ACL | Set-Acl -Path $Path
}

function GeneratePassword {
    $pass = -join ((1..15) | %{get-random -minimum 33 -maximum 127 | %{[char]$_}}) + -join ((1..2) | %{get-random -minimum 33 -maximum 48 | %{[char]$_}}) -replace "c","" -replace "e", "" -replace "C","" -replace "E", "";
    $securePassword = ConvertTo-SecureString $pass -AsPlainText -Force;
    return $securePassword;
}

function RecreateUser {
    param(
        [securestring] $securePassword
    )

    $exists = (Get-LocalUser $CE_USER -ErrorAction Ignore) -as [bool];
    if ($exists) {
        Remove-LocalUser $CE_USER;
    }

    New-LocalUser -User $CE_USER -Password $securePassword -PasswordNeverExpires -FullName "CE" -Description "Special user for running Compiler Explorer";
    Add-LocalGroupMember -Group "Users" -Member $CE_USER;

    ConfigureUserRights -SID (Get-LocalUser $CE_USER).SID
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

function ConfigureUserRights {
    param(
        [String] $SID
    )

    $tmpfile = "c:\tmp\secpol.cfg"
    secedit /export /cfg $tmpfile
    $secpol = (Get-Content $tmpfile)

    $Value = $secpol | Where-Object{ $_ -like "SeBatchLogonRight*" }
    $Index = [array]::IndexOf($secpol,$Value)

    $NewValue = $Value + ",*" + $SID
    $secpol.item($Index) = $NewValue

    $secpol | out-file $tmpfile -Force
    secedit /configure /db c:\windows\security\local.sdb /cfg $tmpfile
    Remove-Item -Path $tmpfile

    gpupdate /Force
}

function InstallAsSystemService {
    param(
        [string] $Name,
        [string] $Exe,
        [array] $Arguments,
        [string] $WorkingDirectory
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

    Write-Host "nssm.exe set $Name AppExit Default Exit"
    /nssm/win64/nssm.exe set $Name AppExit Default Exit

    Write-Host "nssm.exe set $Name Start SERVICE_DEMAND_START"
    /nssm/win64/nssm.exe set $Name Start SERVICE_DEMAND_START

    Write-Host "nssm.exe reset $Name ObjectName"
    /nssm/win64/nssm.exe reset $Name ObjectName

    Write-Host "nssm.exe start $Name"
    /nssm/win64/nssm.exe start $Name
}

function InstallAsService {
    param(
        [string] $Name,
        [string] $Exe,
        [array] $Arguments,
        [string] $WorkingDirectory,
        [PSCredential] $User,
        [securestring] $Password
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

    Write-Host "nssm.exe set $Name AppExit Default Exit"
    /nssm/win64/nssm.exe set $Name AppExit Default Exit

    $Username = $Credential.GetNetworkCredential().Username
    $PlainTextPassword = ConvertFrom-SecureString -SecureString $Password -AsPlainText

    Write-Host "nssm.exe set $Name ObjectName $env:COMPUTERNAME\$Username ..."
    /nssm/win64/nssm.exe set $Name ObjectName "$env:COMPUTERNAME\$Username" "$PlainTextPassword"

    Write-Host "nssm.exe start $Name"
    /nssm/win64/nssm.exe start $Name
}

function InstallAndRunCEAsSystem {
    $SMBServer = GetSMBServerIP -CeEnv $CE_ENV

    $runargs = ("c:\tmp\infra\init\run.ps1","-LogHost",$loghost,"-LogPort",$logport,"-CeEnv",$CE_ENV,"-HostnameForLogging",$betterComputerName,"-SMBServer",$SMBServer) -join " "

    InstallAsSystemService -Name "ce" -Exe "C:\Program Files\PowerShell\7\pwsh.exe" -WorkingDirectory "C:\tmp" -Arguments $runargs
}

function InstallCERunTask {
    param(
        [PSCredential] $Credential,
        [securestring] $Password,
        [string] $CeEnv,
        [string] $HostnameForLogging,
        [string] $SMBServer
    )

    $runargs = ("c:\tmp\infra\init\run.ps1","-LogHost",$loghost,"-LogPort",$logport,"-CeEnv",$CeEnv,"-HostnameForLogging",$HostnameForLogging,"-SMBServer",$SMBServer) -join " "

    InstallAsService -Name "ce" -Exe "C:\Program Files\PowerShell\7\pwsh.exe" -WorkingDirectory "C:\tmp" -Arguments $runargs -User $Credential -Password $Password
}

function ConfigureFileRights {
    DenyAccessByCE -Path "C:\Program Files\Grafana Agent\agent-config.yaml"
    DenyAccessByCE -Path "C:\tmp\log\cestartup-svc.log"
}

function CreateCredAndRun {
    $pass = GeneratePassword;
    RecreateUser $pass;
    $credential = New-Object System.Management.Automation.PSCredential($CE_USER,$pass);

    ConfigureFileRights

    $SMBServer = GetSMBServerIP -CeEnv $CE_ENV

    InstallCERunTask -Credential $credential -Password $pass -CeEnv $CE_ENV -HostnameForLogging $betterComputerName -SMBServer $SMBServer
}

function GetLatestCEWrapper {
    Write-Host "Fetching latest CEWrapper.exe"
    Copy-Item -Path "Y:/cewrapper/cewrapper.exe" -Destination "/tmp/cewrapper.exe"
    New-Item -Path "/cewrapper" -ItemType Directory -Force
    Move-Item -Path "/tmp/cewrapper.exe" -Destination "/cewrapper/cewrapper.exe" -Force
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
    if ($CeEnv -like "*staging") {
        $configPath = "/compiler-explorer/smbserverStaging"
    } elseif ($CeEnv -like "*test") {
        $configPath = "/compiler-explorer/smbserverTest"
    }

    $smbserver = GetConf -Name $configPath -Default "smb-address-unknown";

    return $smbserver
}

function MountY {
    $exists = (Get-SmbMapping Y:) -as [bool]
    if ($exists) {
        Write-Host "Already mapped"
        return
    }

    $smb_ip = GetSMBServerIP -CeEnv "prod"
    while (-not $exists) {
        try {
            Write-Host "Mapping Y:"
            $exists = (New-SmbMapping -LocalPath "Y:" -RemotePath "\\$smb_ip\winshared") -as [bool]
        } catch {
            Write-Host "New-SmbMapping for Y:\ -> \\$smb_ip\winshared failed: $_"
        }
    }
}

function UnMountY {
     Remove-SmbMapping -LocalPath 'Y:' -Force
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

function AddConanToHostsAndFirewall {
    $hostname = "conan.compiler-explorer.com"
    $ip = "18.160.18.12"

    $content = Get-Content "C:\Windows\System32\drivers\etc\hosts"
    $content = $content,($ip + " " + $hostname)
    Set-Content -Path "C:\Windows\System32\drivers\etc\hosts" -Value $content

    netsh advfirewall firewall add rule name="Allow IP for $hostname" dir=out remoteip="$ip" action=allow enable=yes
}

function AddLocalHost {
    $content = Get-Content "C:\Windows\System32\drivers\etc\hosts"
    $content = $content,("127.0.0.1 localhost")
    Set-Content -Path "C:\Windows\System32\drivers\etc\hosts" -Value $content
}

function ConfigureFirewall {
    netsh advfirewall firewall add rule name="TCP Port 80" dir=in action=allow protocol=TCP localport=80 enable=yes
    netsh advfirewall firewall add rule name="TCP Port 80" dir=out action=allow protocol=TCP localport=80 enable=yes

    netsh advfirewall firewall add rule name="allow nginx all" dir=out program="c:\nginx\nginx.exe" action=allow enable=yes
    netsh advfirewall firewall add rule name="allow node all" dir=in program="C:\Program Files\nodejs\node.exe" action=allow enable=yes

    netsh advfirewall firewall add rule name="agent-windows all out" dir=out program="C:\Program Files\Grafana Agent\agent-windows-amd64.exe" action=allow enable=yes

    netsh advfirewall firewall add rule name="allow ssm-agent all out" dir=out program="C:\Program Files\Amazon\SSM\ssm-agent-worker.exe" action=allow enable=yes
    netsh advfirewall firewall add rule name="allow ssm-agent all in" dir=in program="C:\Program Files\Amazon\SSM\ssm-agent-worker.exe" action=allow enable=yes
    netsh advfirewall firewall add rule name="allow ssm-session all out" dir=out program="C:\Program Files\Amazon\SSM\ssm-session-worker.exe" action=allow enable=yes
    netsh advfirewall firewall add rule name="allow ssm-session all in" dir=in program="C:\Program Files\Amazon\SSM\ssm-session-worker.exe" action=allow enable=yes

    $ip = GetSMBServerIP -CeEnv $CE_ENV
    netsh advfirewall firewall add rule name="Allow IP $ip out" dir=out remoteip="$ip" action=allow enable=yes
    netsh advfirewall firewall add rule name="Allow IP $ip in" dir=in remoteip="$ip" action=allow enable=yes

    AddLocalHost

    $ip = "169.254.169.254"
    netsh advfirewall firewall add rule name="Allow IP $ip out" dir=out remoteip="$ip" action=allow enable=yes
    netsh advfirewall firewall add rule name="Allow IP $ip in" dir=in remoteip="$ip" action=allow enable=yes

    $restrict = ((GetLogHost), "ssm.us-east-1.amazonaws.com", "ssmmessages.us-east-1.amazonaws.com", "ec2messages.us-east-1.amazonaws.com", "s3.amazonaws.com", "s3.us-east-1.amazonaws.com", "compiler-explorer-logs.s3.us-east-1.amazonaws.com", "prometheus-us-central1.grafana.net")
    foreach ($hostname in $restrict) {
        $ip = AddToHosts $hostname
        netsh advfirewall firewall add rule name="Allow IP for $hostname" dir=out remoteip="$ip" action=allow enable=yes
    }

    AddConanToHostsAndFirewall

    # should disable dns, but has consequences to figure out
    netsh advfirewall firewall delete rule name="Core Networking - DNS (UDP-Out)"

    netsh advfirewall set publicprofile firewallpolicy blockinbound,blockoutbound
}

ConfigureSmbRights

MountY

GetLatestCEWrapper

UnMountY

InitializeAgentConfig

update_code

# these are only the wintest, the normal amazonwin.properties should be in the CE repo
Write-Host "Installing properties files"
Invoke-WebRequest -Uri "https://raw.githubusercontent.com/compiler-explorer/windows-docker/main/c++.win32.properties" -OutFile "$DEPLOY_DIR/etc/config/c++.wintest.properties"
Invoke-WebRequest -Uri "https://raw.githubusercontent.com/compiler-explorer/windows-docker/main/pascal.win32.properties" -OutFile "$DEPLOY_DIR/etc/config/pascal.wintest.properties"

$loghost = GetLogHost
$logport = GetLogPort

ConfigureFirewall

#CreateCredAndRun
InstallAndRunCEAsSystem
