
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

$env:NODE_ENV = "production"
$env:PATH = "$env:PATH;Z:/compilers/mingw-8.1.0/mingw64/bin"

$nodeargs = ("--max_old_space_size=6000","-r","esm","--","app.js","--dist","--logHost",(GetLogHost),"--logPort",(GetLogPort),"--env","win32","--language","c++,pascal")
#$nodeargs = ("--max_old_space_size=6000","-r","esm","-r","ts-node/register","--","app.js","--dist","--logHost",(GetLogHost),"--logPort",(GetLogPort),"--env","win32","--language","c++,pascal")

Set-Location -Path "C:\compilerexplorer"
#Set-Location -Path "D:\git\compiler-explorer"

& 'C:\Program Files\nodejs\node.exe' $nodeargs
#& 'D:\Program Files\nodejs\node.exe' $nodeargs
