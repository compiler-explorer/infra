
param(
    $LogHost,
    $LogPort,
    $CeEnv,
    $HostnameForLogging,
    $SMBServer
)

function MountZ {
    $exists = (Get-SmbMapping -LocalPath 'Z:') -as [bool]
    if ($exists) {
         Remove-SmbMapping -LocalPath 'Z:' -Force
         $exists = $False
    }

    while (-not $exists) {
        try {
            Write-Host "Mapping Z:"
            $exists = (New-SmbMapping -LocalPath 'Z:' -RemotePath "\\$SMBServer\winshared") -as [bool]
        } catch {
        }
    }
}

MountZ

$env:NODE_ENV = "production"
$env:PATH = "$env:PATH;Z:/compilers/mingw-8.1.0/mingw64/bin"

$nodeargs = (
    "--max_old_space_size=6000", "--", "app.js",
    "--debug", "--prop-debug",
    "--dist",
    "--port", "10240",
    "--metrics-port", "10241",
    "--suppress-console-log",
    "--log-host", $LogHost,
    "--log-port", $LogPort,
    "--hostname-for-logging", $HostnameForLogging,
    "--env", "amazonwin",
    "--env", $CeEnv,
    "--language", "c",
    "--language", "c++"
)

Set-Location -Path "C:\compilerexplorer"

& 'C:\Program Files\nodejs\node.exe' $nodeargs
