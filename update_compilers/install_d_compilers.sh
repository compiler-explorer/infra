#!/bin/bash

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
. ${SCRIPT_DIR}/common.inc "$@"


getgdc() {
    vers=$1
    build=$2
    if [[ -d gdc${vers} ]]; then
        echo D ${vers} already installed, skipping
        return
    fi
    mkdir gdc${vers}
    pushd gdc${vers}
    fetch ftp://ftp.gdcproject.org/binaries/${vers}/x86_64-linux-gnu/gdc-${vers}+${build}.tar.xz | tar Jxf -
    # stripping the D libraries seems to upset them, so just strip the exes
    do_strip x86_64-pc-linux-gnu/bin
    do_strip x86_64-pc-linux-gnu/libexec
    popd
}

getldc() {
    vers=$1
    if [[ -d ldc${vers} ]]; then
        echo LDC ${vers} already installed, skipping
        return
    fi
    mkdir ldc${vers}
    pushd ldc${vers}
    fetch https://github.com/ldc-developers/ldc/releases/download/v${vers}/ldc2-${vers}-linux-x86_64.tar.xz | tar Jxf -
    # any kind of stripping upsets ldc
    popd
}

getldc_s3() {
    vers=$1
    if [[ -d ldc2-${vers} ]]; then
        echo LDC ${vers} already installed, skipping
        return
    fi
    fetch https://s3.amazonaws.com/compiler-explorer/opt/ldc2-${vers}.tar.xz | tar Jxf -
}

getldc_latestbeta() {
    vers=$(fetch https://ldc-developers.github.io/LATEST_BETA)
    if [[ ! -d ldcbeta ]]; then
        mkdir ldcbeta
    fi
    pushd ldcbeta
    if [[ "$(cat .version)" = "${vers}" ]]; then
        echo "LDC beta version ${vers} already installed, skipping"
        popd
        return
    fi
    rm -rf *
    fetch https://github.com/ldc-developers/ldc/releases/download/v${vers}/ldc2-${vers}-linux-x86_64.tar.xz | tar Jxf - --strip-components 1
    echo "${vers}" > .version
    # any kind of stripping upsets ldc
    popd
}

getdmd_2x() {
    VER=$1
    DIR=dmd-${VER}
    if [[ -d ${DIR} ]]; then
        echo DMD ${VER} already installed, skipping
        return
    fi
    mkdir ${DIR}
    pushd ${DIR}
    fetch http://downloads.dlang.org/releases/2.x/${VER}/dmd.${VER}.linux.tar.xz | tar Jxf -
    popd
}

getdmd2_nightly() {
    DIR=dmd2-nightly
    if [[ -d ${DIR} ]]; then
        rm -rf ${DIR}
    fi
    mkdir ${DIR}
    pushd ${DIR}
    fetch https://nightlies.dlang.org/dmd-nightly/dmd.master.linux.tar.xz | tar Jxf -
    popd
}

getgdc 4.8.2 2.064.2
getgdc 4.9.3 2.066.1
getgdc 5.2.0 2.066.1


for version in \
    0.17.2 \
    1.{0,1,2,3,4,5,6,7,8,9,10}.0 \
; do
    getldc ${version}
done
if install_nightly; then
    getldc_latestbeta
fi

getldc_s3 1.2.0
getdmd_2x 2.078.3
getdmd_2x 2.079.0
getdmd_2x 2.079.1
getdmd_2x 2.080.1
getdmd_2x 2.081.2
getdmd_2x 2.082.0

# dmd nightly disabled: server seems to be down/hanging since at least second week of September 2018
#if install_nightly; then
#    getdmd2_nightly
#fi
