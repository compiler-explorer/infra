#!/bin/bash
# Runs the win-compiler-discovery.yml steps directly on admin, for when admin's GitHub runner is busy.
# Usage: run-win-discovery-on-admin.sh gh-NNNNN [winstaging|winprod]
# Run from the infra repo root on the workstation.

set -euo pipefail

BUILD=${1:?usage: $0 gh-NNNNN [winstaging|winprod]}
ENVIRONMENT=${2:-winstaging}

read -r -d '' REMOTE <<'EOF' || true
set -euo pipefail
export PYTHONUNBUFFERED=1
CE=/home/ubuntu/infra/bin/ce
cd /home/ubuntu/infra
git pull -q
$CE win-runner status | grep -q "status: stopped$" || { echo "Windows runner is not stopped; a discovery may be in flight"; exit 1; }
$CE --env winrunner builds set_current "$BUILD" --branch main --confirm
trap "$CE win-runner stop" EXIT
$CE win-runner start
$CE win-runner discovery 2>&1 | tail -20
$CE win-runner uploaddiscovery "$ENVIRONMENT" "$BUILD"
EOF

B64=$(printf 'BUILD=%q\nENVIRONMENT=%q\n%s' "$BUILD" "$ENVIRONMENT" "$REMOTE" | base64 -w0)
bin/ce admin exec -- bash -c "echo $B64 | base64 -d | bash"
aws s3 ls "s3://compiler-explorer/dist/discovery/$ENVIRONMENT/$BUILD.json"
