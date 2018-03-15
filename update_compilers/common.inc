OPT=/opt/compiler-explorer

set -ex
mkdir -p ${OPT}
cd ${OPT}

s3get() {
    aws s3 cp --force $*
}

# Grossly assumes the same proxy for http, https and ftp
fetch() {
    curl ${http_proxy:+--proxy $http_proxy} -L "$*"
}

do_unzip() {
    unzip "$*"
}

do_strip() {
    find $1 -executable -type f | xargs strip || true
    find $1 -executable -type f | xargs --max-procs=$(nproc) -n 1 -I '{}' bash -c 'upx {} || true'
}
