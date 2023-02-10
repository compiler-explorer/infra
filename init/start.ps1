do {
  $ping = test-connection -comp "s3.amazonaws.com" -count 1 -Quiet
} until ($ping)

New-SmbMapping -GlobalMapping -LocalPath 'Z:' -RemotePath '\\172.30.0.29\winshared'

$env:CE_ENV = Invoke-WebRequest -Uri "http://169.254.169.254/latest/user-data" -UseBasicParsing
$DEPLOY_DIR = "/compilerexplorer"
$CE_ENV = $env:CE_ENV
$CE_USER = "ce"

Set-DefaultAWSRegion -Region us-east-1

function GetBetterHostname {
    $meta = Invoke-WebRequest -Uri http://169.254.169.254/latest/meta-data/hostname -UseBasicParsing
    return $meta.Content -replace ".ec2.internal",""
}

$env:COMPUTERNAME = GetBetterHostname

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

update_code

# todo: this should be configured into the build
Write-Host "Installing properties files"
Invoke-WebRequest -Uri "https://raw.githubusercontent.com/compiler-explorer/windows-docker/main/compiler-explorer.local.properties" -OutFile "$DEPLOY_DIR/etc/config/compiler-explorer.local.properties"
Invoke-WebRequest -Uri "https://raw.githubusercontent.com/compiler-explorer/windows-docker/main/c++.win32.properties" -OutFile "$DEPLOY_DIR/etc/config/c++.win32.properties"
Invoke-WebRequest -Uri "https://raw.githubusercontent.com/compiler-explorer/windows-docker/main/pascal.win32.properties" -OutFile "$DEPLOY_DIR/etc/config/pascal.win32.properties"

function GetConf {
    Param(
        $Name
    )

    try {
        return (Get-SSMParameterValue -Name $Name).Parameters.Value;
    }
    catch {
        return ""
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
        $securePassword
    )

    $exists = (Get-LocalUser $CE_USER -ErrorAction Ignore) -as [bool];
    if ($exists) {
        Remove-LocalUser $CE_USER;
    }

    New-LocalUser -User $CE_USER -Password $securePassword -PasswordNeverExpires -FullName "CE" -Description "Special user for running Compiler Explorer";
    Add-LocalGroupMember -Group "Users" -Member $CE_USER;

    ConfigureUserRights -SID (Get-LocalUser $CE_USER).SID
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
    secedit /configure /db c:\windows\security\local.sdb /cfg $tmpfile /areas USER_RIGHTS
    Remove-Item -Path $tmpfile

    gpupdate /Force
}

function InstallCERunTask {
    param(
        [PSCredential] $Credential
    )

    Unregister-ScheduledTask "CE" -Confirm:$false

    $Settings = New-ScheduledTaskSettingsSet -DontStopOnIdleEnd
    $Settings.ExecutionTimeLimit = "PT0S"

    $Username = $Credential.GetNetworkCredential().Username
    $Password = $Credential.GetNetworkCredential().Password

    $runargs = ("c:\tmp\infra\init\run.ps1","-LogHost",(GetLogHost),"-LogPort",(GetLogPort)) -join " "

    $TaskParams = @{
        #Action = New-ScheduledTaskAction -Execute "pwsh" -Argument "D:\git\compiler-explorer-image\init\run.ps1"
        Action = New-ScheduledTaskAction -Execute "pwsh" -Argument $runargs
        Trigger = Get-CimClass "MSFT_TaskRegistrationTrigger" -Namespace "Root/Microsoft/Windows/TaskScheduler"
        Principal = New-ScheduledTaskPrincipal -UserId $Username -LogonType Password
        Settings = $Settings
    }

    New-ScheduledTask @TaskParams | Register-ScheduledTask "CE" -User $Username -Password $Password

    Start-ScheduledTask "CE"
}

function CreateCredAndRun {
    $pass = GeneratePassword;
    RecreateUser $pass;
    $credential = New-Object System.Management.Automation.PSCredential($CE_USER,$pass);
    # DenyAccessByCE -Path "C:\Program Files\Grafana Agent\agent-config.yaml"

    InstallCERunTask -Credential $credential
}

CreateCredAndRun
