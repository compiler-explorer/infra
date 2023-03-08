
param(
    $LogHost,
    $LogPort,
    $CeEnv
)

function MountZ {
    $exists = (Get-SmbMapping -LocalPath 'Z:') -as [bool]
    if ($exists) {
         Write-Host "Already mapped"
         return
    }

    while (-not $exists) {
        try {
            Write-Host "Mapping Z:"
            $exists = (New-SmbMapping -LocalPath 'Z:' -RemotePath '\\172.30.0.29\winshared') -as [bool]
        } catch {
        }
    }
}

MountZ

$env:NODE_ENV = "production"
#$env:PATH = "$env:PATH;Z:/compilers/mingw-8.1.0/mingw64/bin"

$nodeargs = ("--max_old_space_size=6000","--","app.js","--debug","--dist","--port","10240","--metricsPort","10241","--suppressConsoleLog","--logHost",$LogHost,"--logPort",$LogPort,"--env","amazonwin","--env",$CeEnv,"--language","c++,pascal")

Set-Location -Path "C:\compilerexplorer"
#Set-Location -Path "D:\git\compiler-explorer"

& 'C:\Program Files\nodejs\node.exe' $nodeargs >> /tmp/node-log.txt
#& 'D:\Program Files\nodejs\node.exe' $nodeargs
