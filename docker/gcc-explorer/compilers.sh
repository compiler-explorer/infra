#/bin/bash

set -e
cd /opt

find /opt -executable -type f | xargs strip || true
