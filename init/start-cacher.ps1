
param(
    [String] $Compiler
)



do {
  $ping = test-connection -comp "s3.amazonaws.com" -count 1 -Quiet
} until ($ping)

[Environment]::SetEnvironmentVariable("PYTHON_KEYRING_BACKEND", 'keyring.backends.null.Keyring', [System.EnvironmentVariableTarget]::Process);

$env:PATH = "$env:PATH;C:\BuildTools\Python;C:\BuildTools\Python\Scripts;C:\BuildTools\Ninja;Z:\compilers\windows-kits-10\bin;C:\BuildTools\CMake\bin;Z:\compilers\mingw-w64-13.1.0-16.0.2-11.0.0-ucrt-r1\bin;C:\Program Files\7-Zip;C:\Program Files\Amazon\AWSCLIV2"

function FetchInfra {
    Set-Location -Path "/tmp"

    $infra = "/tmp/infra"
    if (Test-Path -Path $infra) {
        Set-Location -Path "/tmp/infra"

        Remove-Item -Path ".env" -Recurse
        Remove-Item -Path ".venv" -Recurse
        Remove-Item -Path ".poetry" -Recurse
        Remove-Item -Path ".mypy_cache" -Recurse

        git reset --hard
        git pull
        git checkout add-compiler-cache-extraction
    } else {
        git clone https://github.com/compiler-explorer/infra --branch add-compiler-cache-extraction
    }

    Set-Location -Path "/tmp/infra"
    & ./ce_install.ps1 --help
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


Set-Location /tmp/infra


$FORCECOMPILERPARAM = ""
# if ( $Compiler -ne "all" ) {
#   $FORCECOMPILERPARAM = "--compiler-id $Compiler"
# }

pwsh .\ce_install.ps1 --staging-dir "C:/tmp/staging" --dest "C:/tmp/staging" compilercache extract $FORCECOMPILERPARAM --platform windows
