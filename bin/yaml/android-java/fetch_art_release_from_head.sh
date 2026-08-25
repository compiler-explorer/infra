#!/bin/bash

# Fetches ART binaries and ART bootclasspath jars from AOSP head.
# Saves the result at `art_release.zip`.

set -euo pipefail

BRANCH=aosp-android-latest-release
TARGET=aosp_cf_x86_64_only_phone-userdebug

# ci.android.com's legacy API no longer serves unauthenticated requests: the
# /builds/latest/... endpoint we used to follow a redirect from now answers 403
# "You must migrate to Build API v4". status.json still works, so resolve the
# build number from there instead.
BUILD=$(curl -sS --fail "https://ci.android.com/builds/branches/${BRANCH}/status.json" |
    python3 -c 'import json, sys; print(next(t["last_known_good_build"] for t in json.load(sys.stdin)["targets"] if t["name"] == sys.argv[1]))' "${TARGET}")
echo "Fetching ART release from ${BRANCH} build ${BUILD}"

# Only GET works here; a HEAD request on this path 404s.
curl -sS --fail --location --output art_release.zip \
    "https://ci.android.com/builds/submitted/${BUILD}/${TARGET}/latest/raw/art_release.zip"
