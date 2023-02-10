
param(
    $LogHost,
    $LogPort
)

$env:NODE_ENV = "production"
$env:PATH = "$env:PATH;Z:/compilers/mingw-8.1.0/mingw64/bin"

$nodeargs = ("--max_old_space_size=6000","-r","esm","--","app.js","--dist","--port","80","--metricsPort","10241","--suppressConsoleLog","--logHost",$LogHost,"--logPort",$LogPort,"--env","win32","--language","c++,pascal")

Set-Location -Path "C:\compilerexplorer"
#Set-Location -Path "D:\git\compiler-explorer"

& 'C:\Program Files\nodejs\node.exe' $nodeargs
#& 'D:\Program Files\nodejs\node.exe' $nodeargs
