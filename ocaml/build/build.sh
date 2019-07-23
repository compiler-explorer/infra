#!/bin/bash

set -ex

FULL_VERSION=$1
IS_AUTOCONF=$3
VERSION=${FULL_VERSION}
FLAGS=
if echo ${VERSION} | grep -- '-flambda'; then
    if [[ "x$IS_AUTOCONF" -eq "xyes" ]]; then
        FLAGS=--enable-flambda
    else
        FLAGS=-flambda
    fi
    VERSION=${VERSION%-flambda}
fi

if echo ${VERSION} | grep 'trunk'; then
    echo Not supported at present
    exit 1
fi

OUTPUT=/root/ocaml-${FULL_VERSION}.tar.xz
S3OUTPUT=""
if echo $2 | grep s3://; then
    S3OUTPUT=$2
else
    OUTPUT=${2-/root/ocaml-${VERSION}.tar.xz}
fi

# Ocaml likes to put shebang lines of the form #!/path/to/ocamlrun which is set during build.
# We can't reolcate ocaml after the build, so we build it here in its presumed final destination location
STAGING_DIR=/opt/compiler-explorer/ocaml-${FULL_VERSION}
rm -rf ${STAGING_DIR}
mkdir -p ${STAGING_DIR}

curl -L https://github.com/ocaml/ocaml/archive/${VERSION}.tar.gz | tar zxf -
cd ocaml-${VERSION}
./configure ${FLAGS} -prefix ${STAGING_DIR}
make -j$(nproc) world.opt
make -j$(nproc) install

export XZ_DEFAULTS="-T 0"
tar Jcf ${OUTPUT} --transform "s,^./,./ocaml-${FULL_VERSION}/," -C ${STAGING_DIR} .

if [[ ! -z "${S3OUTPUT}" ]]; then
    s3cmd put --rr ${OUTPUT} ${S3OUTPUT}
fi
