OPT=/opt/compiler-explorer
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

set -ex
set -o pipefail
mkdir -p ${OPT}
cd ${OPT}

s3get() {
    local PRESIGNED_URL
    PRESIGNED_URL=$(aws s3 presign $1)
    curl -s ${http_proxy:+--proxy $http_proxy} -L "$PRESIGNED_URL" -o "$2"
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

s3fetch() {
    local PRESIGNED_URL
    PRESIGNED_URL=$(aws s3 presign $1)
    fetch "${PRESIGNED_URL}"
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

CE_INSTALL_ARG=

if install_nightly; then
    CE_INSTALL_ARG="--enable=nightly"
fi

ce_install() {
    "${SCRIPT_DIR}/../bin/ce_install" ${CE_INSTALL_ARG} install "$@"
}

ce_squash() {
    if [[ -d /opt/squash-images ]]; then
        "${SCRIPT_DIR}/../bin/ce_install" squash "$@"
    else
        echo "Skipping ce squash of $@ as target directory doesn't exist"
    fi
}

PATCHELF=${OPT}/patchelf-0.8/src/patchelf
