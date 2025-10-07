
param(
    $LogHost,
    $LogPort,
    $CeEnv,
    $HostnameForLogging,
    $SMBServer,
    $InstanceColor = $null
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

function MountY {
    $exists = (Get-SmbMapping -LocalPath 'Y:') -as [bool]
    if ($exists) {
         Remove-SmbMapping -LocalPath 'Y:' -Force
         $exists = $False
    }

    while (-not $exists) {
        try {
            Write-Host "Mapping Y:"
            $exists = (New-SmbMapping -LocalPath 'Y:' -RemotePath "\\$SMBServer\winshared") -as [bool]
        } catch {
        }
    }
}

function Wait-ForDrive {
    param(
        [Parameter(Mandatory=$true)]
        [string]$DriveLetter,
        [int]$CheckIntervalSeconds = 1
    )

    Write-Host "Waiting for drive $DriveLetter`:\" -ForegroundColor Yellow
    while ($true) {
        Start-Sleep -Seconds $CheckIntervalSeconds

        # Check if the specific drive is available
        $currentDrives = Get-PSDrive -PSProvider FileSystem | Where-Object { $_.Name.Length -eq 1 } | Select-Object -ExpandProperty Name

        if ($currentDrives -contains $DriveLetter) {
            Write-Host "`nDrive $DriveLetter`:\ is now available!" -ForegroundColor Green
            return $true
        }

        Write-Host "." -NoNewline -ForegroundColor DarkGray
    }
}

#if (Test-Path "C:\tmp\cewinfilecache\CeWinFileCacheFS.exe") {
  #MountY
  #Start-Process "C:\tmp\cewinfilecache\CeWinFileCacheFS.exe" -WorkingDirectory "C:\tmp\cewinfilecache" -ArgumentList "--mount Z: --log-level debug --config compilers.production.json" -RedirectStandardOutput "C:\tmp\cewinfilecache\output.log" -RedirectStandardError "C:\tmp\cewinfilecache\error.log" -NoNewWindow
  #Wait-ForDrive -DriveLetter 'Z' -CheckIntervalSeconds 1
#} else {
  MountZ
#}

$env:NODE_ENV = "production"
$env:PATH = "$env:PATH;Z:/compilers/mingw-8.1.0/mingw64/bin"

$nodeargs = @(
    "--max_old_space_size=6000", "--", "app.js",
#    "--debug", "--prop-debug",
    "--dist",
    "--port", "10240",
    "--metrics-port", "10241",
    "--suppress-console-log",
    "--log-host", $LogHost,
    "--log-port", $LogPort,
    "--hostname-for-logging", $HostnameForLogging
)

# if ($InstanceColor) {
    # $nodeargs += @("--instance-color", $InstanceColor)
# }

$nodeargs += @(
    "--env", "amazonwin",
    "--env", $CeEnv,
    "--language", "c",
    "--language", "c++",
    "--language", "hlsl"
)

Set-Location -Path "C:\compilerexplorer"

& 'C:\Program Files\nodejs\node.exe' $nodeargs
