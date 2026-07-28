$ErrorActionPreference = 'Stop'

$DEPLOY_DIR = "C:\compilerexplorer"
$OUTPUT = "C:\tmp\discovered-compilers.json"

# Discovery targets winprod: winstaging serves the same compilers from the same share, and the
# per-environment properties only differ in httpRoot, motdUrl and sentryEnvironment.
$CE_ENV = "winprod"

function GetSMBServerIP {
    return (aws ssm get-parameter --name "/compiler-explorer/smbserverProd" | ConvertFrom-Json).Parameter.Value
}

function MountZ {
    # SMB mappings belong to a logon session, so the one init/run.ps1 makes as LocalSystem is
    # invisible here. Every path in the amazonwin properties is Z:\..., so map it ourselves.
    $exists = (Get-SmbMapping -LocalPath 'Z:' -ErrorAction SilentlyContinue) -as [bool]
    if ($exists) {
        Remove-SmbMapping -LocalPath 'Z:' -Force
    }

    $smbServer = GetSMBServerIP
    Write-Host "Mapping Z: to \\$smbServer\winshared"
    New-SmbMapping -LocalPath 'Z:' -RemotePath "\\$smbServer\winshared" | Out-Null
}

MountZ

$env:NODE_ENV = "production"
$env:PATH = "$env:PATH;Z:/compilers/mingw-8.1.0/mingw64/bin"

Remove-Item -Path $OUTPUT -Force -ErrorAction SilentlyContinue

$nodeargs = @(
    "--max_old_space_size=6000", "--", "app.js",
    "--discoveryonly", $OUTPUT,
    "--exit-on-compiler-failure",
    "--dist",
    "--port", "10240",
    "--metrics-port", "10241",
    "--suppress-console-log",
    "--env", "amazonwin",
    "--env", $CE_ENV,
    "--language", "c",
    "--language", "c++",
    "--language", "hlsl"
)

Set-Location -Path $DEPLOY_DIR

& 'C:\Program Files\nodejs\node.exe' $nodeargs

if (-not (Test-Path $OUTPUT)) {
    throw "Discovery did not produce $OUTPUT"
}

Write-Host "Discovery written to $OUTPUT"
