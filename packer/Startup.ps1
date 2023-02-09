Remove-Item -Path "/tmp/infra" -Force -Recurse

git clone https://github.com/compiler-explorer/infra /tmp/infra

/tmp/infra/init/start.ps1
