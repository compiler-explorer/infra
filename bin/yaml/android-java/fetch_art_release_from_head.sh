#!/bin/bash

# Fetches ART binaries and ART bootclasspath jars from AOSP head.
# Saves the result at `art_release.zip`.

set -euo pipefail

URL=https://ci.android.com/builds/latest/branches/aosp-main/targets/aosp_arm64-trunk_staging-userdebug/view/BUILD_INFO
RURL=$(curl -Ls -o /dev/null -w "%{url_effective}" "${URL}")
curl "${RURL%/view/BUILD_INFO}/raw/art_release.zip" --location --output art_release.zip
