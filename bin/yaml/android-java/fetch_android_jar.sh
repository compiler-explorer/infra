#!/bin/bash

set -euo pipefail

URL=https://ci.android.com/builds/submitted/$1/sdk/latest/view/BUILD_INFO
RURL=$(curl -Ls -o /dev/null -w "%{url_effective}" "${URL}")
curl "${RURL%/view/BUILD_INFO}/raw/android_system.jar" --location --output android.jar
