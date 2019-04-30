OPT=/opt/compiler-explorer
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

set -ex
set -o pipefail
mkdir -p ${OPT}
cd ${OPT}

s3get() {
    aws s3 cp --force $*
}

# Grossly assumes the same proxy for http, https and ftp
fetch() {
    # We've had so many problems with pipes on the admin box. This is terrible,
    # but is reliable. I tried using buffer(1) and mbuffer(1), but they didn't
    # work either.
    local temp="$(mktemp)"
    curl -s ${http_proxy:+--proxy $http_proxy} -L "$*" -o "$temp"
    cat "$temp"
    rm "$temp"
}

do_unzip() {
    unzip "$*"
}

do_strip() {
    find $1 -executable -type f | xargs strip 2>&1 || true
}

ARG1="$1"

install_nightly() {
    if [[ "$ARG1" = "nightly" ]]; then
        return 0
    else
        return 1
    fi
}

PATCHELF=${OPT}/patchelf-0.8/src/patchelf
S3BUCKET=compiler-explorer
SUBDIR=opt
S3URL=https://s3.amazonaws.com/${S3BUCKET}/${SUBDIR}
ALL_COMPILERS=$(${SCRIPT_DIR}/../bin/list_compilers)
