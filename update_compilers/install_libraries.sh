#!/bin/bash

# This script installs all the libraries to be used by Compiler Explorer

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
. ${DIR}/common.inc

#########################
# C++
if [ ! -d "libs/kvasir/mpl/trunk" ]; then
    git clone https://github.com/kvasir-io/mpl.git libs/kvasir/mpl/trunk
    git -C libs/kvasir/mpl/trunk checkout development
else
    git -C libs/kvasir/mpl/trunk pull origin development
fi

install_boost() {
    for VERSION in "$@"; do
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
    done
}

install_boost 1.64.0 1.65.0 1.66.0

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
get_github_versioned_and_trunk libs/google-benchmark google/benchmark v1.2.0 v1.3.0
get_github_versioned_and_trunk libs/rangesv3 ericniebler/range-v3 0.3.0 0.3.5
get_github_versioned_and_trunk libs/dlib davisking/dlib v19.7 v19.9
get_github_versioned_and_trunk libs/libguarded copperspice/libguarded libguarded-1.1.0
get_github_versioned_and_trunk libs/brigand edouarda/brigand 1.3.0
get_github_versioned_and_trunk libs/fmt fmtlib/fmt 4.1.0 4.0.0
get_github_versioned_and_trunk libs/hfsm andrew-gresyk/HFSM 0.8
get_github_versioned_and_trunk_with_quirk libs/eigen eigenteam/eigen-git-mirror v 3.3.4
get_github_versioned_and_trunk libs/glm g-truc/glm 0.9.8.5


#########################
# C
install_gnu_gsl_versioned_and_latest() {
    # We need to build this, I think?
    local DIR=$1
    shift
    mkdir -p $DIR
    get_or_sync ${DIR}/trunk https://git.savannah.gnu.org/git/gsl.git
    for tag in "$@"; do
        get_if_not_there ${DIR}/${tag} ftp://ftp.gnu.org/gnu/gsl/gsl-${tag}.tar.gz
    done
}

#install_gnu_gsl_versioned_and_latest libs/gnu-gsl 2.3 2.4

#########################
# D

if [ ! -d "${OPT}/libs/d/mir-glas-trunk" ]; then
    git clone https://github.com/libmir/mir-glas.git ${OPT}/libs/d/mir-glas-trunk
    git -C ${OPT}/libs/d/mir-glas-trunk checkout master
else
    git -C ${OPT}/libs/d/mir-glas-trunk pull origin master
fi
install_mir_glas() {
    for VERSION in "$@"; do
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
    done
}

install_mir_glas 0.1.5 0.2.3 0.2.4

if [ ! -d "${OPT}/libs/d/mir-algorithm-trunk" ]; then
    git clone https://github.com/libmir/mir-algorithm.git ${OPT}/libs/d/mir-algorithm-trunk
    git -C ${OPT}/libs/d/mir-algorithm-trunk checkout master
else
    git -C ${OPT}/libs/d/mir-algorithm-trunk pull origin master
fi
install_mir_algorithm() {
    for VERSION in "$@"; do
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
    done
}

install_mir_algorithm 0.5.17 0.6.13 0.6.21
