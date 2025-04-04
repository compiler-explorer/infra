#!/bin/bash

# Fetches ART binaries and ART bootclasspath jars from AOSP head.
# Saves the result at `art_release.zip`.

set -euo pipefail

URL=https://ci.android.com/builds/latest/branches/aosp-android-latest-release/targets/aosp_cf_x86_64_only_phone-userdebug/view/BUILD_INFO
PATTERN="(.*\/submitted\/([0-9]+)\/.*)/view/BUILD_INFO$"

RURL=$(curl -Ls -o /dev/null -w "%{url_effective}" "${URL}")
if ! [[ "$RURL" =~ $PATTERN ]]; then
  echo "Got expected URL $RURL"
  exit 1
fi
curl "${BASH_REMATCH[1]}/raw/art_release.zip" --location --output art_release.zip
