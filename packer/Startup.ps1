# The rules init/start.ps1 installs survive a reboot, and they drop DNS and everything outbound
# that is not on a pinned allowlist -- github included. Without this reset the loop below never
# finishes on any boot but the first, so infra is never refreshed and start.ps1 never runs at
# all. start.ps1 re-applies the lockdown once it has what it needs.
netsh advfirewall reset

do {
  $ping = test-connection -comp "github.com" -count 1 -Quiet
} until ($ping)

Remove-Item -Path "/tmp/infra" -Force -Recurse

git clone https://github.com/compiler-explorer/infra /tmp/infra

/tmp/infra/init/start.ps1
