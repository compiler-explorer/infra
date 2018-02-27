#!/bin/bash

# This script installs all the libraries to be used by Compiler Explorer

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
. ${DIR}/common.inc

#########################
# C++

# add kvasir libraries
if [ ! -d "libs/kvasir/mpl/trunk" ]; then
    git clone https://github.com/kvasir-io/mpl.git libs/kvasir/mpl/trunk
    git -C libs/kvasir/mpl/trunk checkout development
else
    git -C libs/kvasir/mpl/trunk pull origin development
fi

install_boost() {
    local VERSION=$1
    local VERSION_UNDERSCORE=$(echo ${VERSION} | tr . _)
    local DEST=${OPT}/libs/boost_${VERSION_UNDERSCORE}/boost/ 
    if [[ ! -d ${DEST} ]]; then
        mkdir -p /tmp/boost
        pushd /tmp/boost
        fetch https://dl.bintray.com/boostorg/release/${VERSION}/source/boost_${VERSION_UNDERSCORE}.tar.bz2 | tar jxf - boost_${VERSION_UNDERSCORE}/boost
        mkdir -p ${OPT}/libs/boost_${VERSION_UNDERSCORE}/boost
        rsync -a boost_${VERSION_UNDERSCORE}/boost/ ${DEST}
        popd
        rm -rf /tmp/boost
    fi
}
install_boost 1.64.0
install_boost 1.65.0
install_boost 1.66.0

get_or_sync() {
    local DIR=$1
    local URL=$2
    if [ ! -d "${DIR}" ]; then
        git clone "${URL}" "${DIR}"
    else
	    git -C "${DIR}" reset --hard
	    git -C "${DIR}" pull
    fi
}

get_or_sync libs/cmcstl2 https://github.com/CaseyCarter/cmcstl2.git
get_or_sync libs/GSL https://github.com/Microsoft/GSL.git
get_or_sync libs/gsl-lite https://github.com/martinmoene/gsl-lite.git
get_or_sync libs/opencv https://github.com/opencv/opencv.git
get_or_sync libs/xtl https://github.com/QuantStack/xtl.git
get_or_sync libs/xsimd https://github.com/QuantStack/xsimd.git
get_or_sync libs/xtensor https://github.com/QuantStack/xtensor.git
get_or_sync libs/abseil https://github.com/abseil/abseil-cpp.git
get_or_sync libs/cctz https://github.com/google/cctz.git
get_or_sync libs/ctre https://github.com/hanickadot/compile-time-regular-expressions.git
get_or_sync libs/cppcoro https://github.com/lewissbaker/cppcoro.git

get_if_not_there() {
    local DIR=$1
    local URL=$2
    if [[ ! -d ${DIR} ]]; then
        mkdir -p ${DIR}
        fetch ${URL} | tar zxf - --strip-components=1 -C ${DIR}
    fi
}

get_github_versioned_and_trunk_with_quirk() {
    local DIR=$1
    local URL=https://github.com/$2
    local QUIRK=$3
    shift 3
    mkdir -p $DIR
    get_or_sync ${DIR}/${QUIRK}trunk ${URL}.git
    local version
    for tag in "$@"; do
        get_if_not_there ${DIR}/${QUIRK}${tag} ${URL}/archive/${tag}.tar.gz
    done
}

get_github_versioned_and_trunk() {
    local DIR=$1
    local URL=$2
    shift 2
    get_github_versioned_and_trunk_with_quirk $DIR $URL '' "$@"
}

get_github_versioned_and_trunk libs/ulib stefanocasazza/ULib v1.4.2
get_github_versioned_and_trunk libs/google-benchmark google/benchmark v1.2.0
get_github_versioned_and_trunk libs/rangesv3 ericniebler/range-v3 0.3.0
get_github_versioned_and_trunk libs/dlib davisking/dlib v19.7
get_github_versioned_and_trunk libs/libguarded copperspice/libguarded libguarded-1.1.0
get_github_versioned_and_trunk libs/brigand edouarda/brigand 1.3.0
get_github_versioned_and_trunk libs/fmt fmtlib/fmt 4.1.0 4.0.0
get_github_versioned_and_trunk_with_quirk libs/eigen eigenteam/eigen-git-mirror v 3.3.4

#########################

#########################
# D

# MIR GLAS
if [ ! -d "${OPT}/libs/d/mir-glas-trunk" ]; then
    git clone https://github.com/libmir/mir-glas.git ${OPT}/libs/d/mir-glas-trunk
    git -C ${OPT}/libs/d/mir-glas-trunk checkout master
else
    git -C ${OPT}/libs/d/mir-glas-trunk pull origin master
fi
install_mir_glas() {
    # https://github.com/libmir/mir-glas/archive/v0.2.3.tar.gz
    local VERSION=$1
    local DEST=${OPT}/libs/d/mir-glas-v${VERSION}/
    if [[ ! -d ${DEST} ]]; then
        mkdir -p /tmp/mir-glas
        pushd /tmp/mir-glas
        fetch https://github.com/libmir/mir-glas/archive/v${VERSION}.tar.gz | tar zxf -
        mkdir -p ${DEST}
        rsync -a mir-glas-${VERSION}/ ${DEST}
        popd
        rm -rf /tmp/mir-glas
    fi
}
install_mir_glas 0.1.5
install_mir_glas 0.2.3

# MIR Algorithm
if [ ! -d "${OPT}/libs/d/mir-algorithm-trunk" ]; then
    git clone https://github.com/libmir/mir-algorithm.git ${OPT}/libs/d/mir-algorithm-trunk
    git -C ${OPT}/libs/d/mir-algorithm-trunk checkout master
else
    git -C ${OPT}/libs/d/mir-algorithm-trunk pull origin master
fi
install_mir_algorithm() {
    # https://github.com/libmir/mir-algorithm/archive/v0.6.11.tar.gz
    local VERSION=$1
    local DEST=${OPT}/libs/d/mir-algorithm-v${VERSION}/
    if [[ ! -d ${DEST} ]]; then
        mkdir -p /tmp/mir-algorithm
        pushd /tmp/mir-algorithm
        fetch https://github.com/libmir/mir-algorithm/archive/v${VERSION}.tar.gz | tar zxf -
        mkdir -p ${DEST}
        rsync -a mir-algorithm-${VERSION}/ ${DEST}
        popd
        rm -rf /tmp/mir-algorithm
    fi
}
install_mir_algorithm 0.5.17
install_mir_algorithm 0.6.13
install_mir_algorithm 0.6.21

#########################

