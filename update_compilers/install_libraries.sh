#!/bin/bash

# This script installs all the libraries to be used by Compiler Explorer

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
. ${DIR}/common.inc

ARG1="$1"
install_nightly() {
    if [[ "$ARG1" = "nightly" ]]; then
        return 0
    else
        return 1
    fi
}

if install_nightly; then
    echo "Installing trunk versions"
else
    echo "Skipping install of trunk versions"
fi

#########################
# C++
if install_nightly; then
if [[ ! -d "libs/kvasir/mpl/trunk" ]]; then
    git clone -q https://github.com/kvasir-io/mpl.git libs/kvasir/mpl/trunk
    git -C libs/kvasir/mpl/trunk checkout -q development
else
    git -C libs/kvasir/mpl/trunk pull -q origin development
fi
fi

if [[ ! -d cmake ]]; then
    mkdir cmake
    fetch https://cmake.org/files/v3.11/cmake-3.11.0-rc3-Linux-x86_64.tar.gz | tar zxf - --strip-components 1 -C cmake
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

install_boost 1.64.0 1.65.0 1.66.0 1.67.0 1.68.0 1.69.0

install_llvm() {
    for VERSION in "$@"; do
        local DEST=${OPT}/libs/llvm/${VERSION}
        local URL=http://releases.llvm.org/${VERSION}/llvm-${VERSION}.src.tar.xz
        if [[ ! -d ${DEST} ]]; then
            rm -rf /tmp/llvm
            mkdir -p /tmp/llvm
            fetch ${URL} | tar Jxf - --strip-components=1 -C /tmp/llvm
            mkdir -p ${DEST}
            pushd ${DEST}
            ${OPT}/cmake/bin/cmake /tmp/llvm 2>&1
            rsync -a /tmp/llvm/include/ include/
            popd
            rm -rf /tmp/llvm
        fi
    done
}

install_llvm_trunk() {
    rm -rf /tmp/llvm
    mkdir -p /tmp/llvm
    svn co -q http://llvm.org/svn/llvm-project/llvm/trunk /tmp/llvm
    mkdir -p libs/llvm/trunk
    pushd libs/llvm/trunk
    ${OPT}/cmake/bin/cmake /tmp/llvm 2>&1
    rsync -a /tmp/llvm/include/ include/
    popd
    rm -rf /tmp/llvm
}

install_llvm 6.0.0 5.0.1 4.0.1

if install_nightly; then
    install_llvm_trunk
fi

get_or_sync() {
    local DIR=$1
    local URL=$2
    if [[ ! -d "${DIR}" ]]; then
        git clone -q "${URL}" "${DIR}"
    else
    	git -C "${DIR}" fetch -q
    	git -C "${DIR}" reset -q --hard origin
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
get_or_sync libs/cppcoro https://github.com/lewissbaker/cppcoro.git
get_or_sync libs/ctbignum https://github.com/niekbouman/ctbignum.git
get_or_sync libs/outcome https://github.com/ned14/outcome.git
get_or_sync libs/cnl https://github.com/johnmcfarlane/cnl.git
get_or_sync libs/googletest https://github.com/google/googletest.git
get_or_sync libs/tbb https://github.com/01org/tbb.git

get_if_not_there() {
    local DIR=$1
    local URL=$2
    if [[ ! -d ${DIR} ]]; then
        mkdir -p ${DIR}
        fetch ${URL} | tar zxf - --strip-components=1 -C ${DIR}
    fi
}

# Alias for get_if_not_there, but better conveys the intention
get_git_version() {
    local DIR=$1
    local URL=$2
    get_if_not_there ${DIR} ${URL}
}

get_github_versions() {
   local DIR=$1
   local URL=https://github.com/$2
   shift 2
   for tag in "$@"; do
       get_git_version ${DIR}/${tag} ${URL}/archive/${tag}.tar.gz
   done
}

get_github_versioned_and_trunk_with_quirk() {
    local DIR=$1
    local REPO=$2
    local URL=https://github.com/${REPO}
    local QUIRK=$3
    shift 3
    mkdir -p ${DIR}
    if install_nightly; then
        get_or_sync ${DIR}/${QUIRK}trunk ${URL}.git
    fi
    for tag in "$@"; do
        get_git_version ${DIR}/${QUIRK}${tag} ${URL}/archive/${tag}.tar.gz
    done
}

get_github_versioned_and_trunk() {
    local DIR=$1
    local URL=$2
    shift 2
    get_github_versioned_and_trunk_with_quirk ${DIR} ${URL} '' "$@"
}

get_github_versioned_and_trunk libs/ulib stefanocasazza/ULib v1.4.2
get_github_versioned_and_trunk libs/google-benchmark google/benchmark v1.2.0 v1.3.0 v1.4.0
get_github_versioned_and_trunk libs/rangesv3 ericniebler/range-v3 0.3.0 0.3.5 0.3.6
get_github_versioned_and_trunk libs/dlib davisking/dlib v19.7 v19.9 v19.10
get_github_versioned_and_trunk libs/libguarded copperspice/libguarded libguarded-1.1.0
get_github_versioned_and_trunk libs/brigand edouarda/brigand 1.3.0
get_github_versioned_and_trunk libs/fmt fmtlib/fmt 5.3.0 5.2.0 5.1.0 5.0.0 4.1.0 4.0.0
get_github_versioned_and_trunk libs/hfsm andrew-gresyk/HFSM 0.8 0.10
get_github_versioned_and_trunk_with_quirk libs/eigen eigenteam/eigen-git-mirror v 3.3.4
get_github_versioned_and_trunk libs/glm g-truc/glm 0.9.8.5 0.9.9.0
get_github_versioned_and_trunk libs/catch2 catchorg/Catch2 v2.2.2 v2.2.3
get_github_versions libs/expected-lite martinmoene/expected-dark v0.0.1
get_github_versioned_and_trunk libs/expected-lite martinmoene/expected-lite v0.1.0
get_github_versioned_and_trunk libs/nlohmann_json nlohmann/json v3.1.2 v2.1.1
get_github_versioned_and_trunk libs/doctest onqtam/doctest 1.2.9 2.0.0 2.0.1 2.1.0 2.2.0 2.2.1
get_github_versioned_and_trunk libs/eastl electronicarts/EASTL 3.12.01

get_github_versions libs/GSL Microsoft/GSL v1.0.0

get_github_versions libs/vcl darealshinji/vectorclass v1.30

install_blaze() {
    for VERSION in "$@"; do
        local DEST=${OPT}/libs/blaze/v${VERSION}/
        if [[ ! -d ${DEST} ]]; then
            mkdir -p /tmp/blaze
            pushd /tmp/blaze
            fetch https://bitbucket.org/blaze-lib/blaze/downloads/blaze-${VERSION}.tar.gz | tar zxf -
            mkdir -p ${DEST}
            rsync -a blaze-${VERSION}/ ${DEST}
            popd
            rm -rf /tmp/blaze
        fi
    done
}

install_blaze 3.3
get_or_sync libs/blaze/trunk https://bitbucket.org/blaze-lib/blaze.git

#########################
# C
install_gnu_gsl_versioned_and_latest() {
    # We need to build this, I think?
    local DIR=$1
    shift
    mkdir -p $DIR
    if install_nightly; then
        get_or_sync ${DIR}/trunk https://git.savannah.gnu.org/git/gsl.git
    fi
    for tag in "$@"; do
        get_if_not_there ${DIR}/${tag} ftp://ftp.gnu.org/gnu/gsl/gsl-${tag}.tar.gz
    done
}

#install_gnu_gsl_versioned_and_latest libs/gnu-gsl 2.3 2.4

#########################
# D
if install_nightly; then
if [ ! -d "${OPT}/libs/d/mir-glas-trunk" ]; then
    git clone -q https://github.com/libmir/mir-glas.git ${OPT}/libs/d/mir-glas-trunk
    git -C ${OPT}/libs/d/mir-glas-trunk checkout -q master
else
    git -C ${OPT}/libs/d/mir-glas-trunk pull -q origin master
fi
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

if install_nightly; then
if [ ! -d "${OPT}/libs/d/mir-algorithm-trunk" ]; then
    git clone -q https://github.com/libmir/mir-algorithm.git ${OPT}/libs/d/mir-algorithm-trunk
    git -C ${OPT}/libs/d/mir-algorithm-trunk checkout -q master
else
    git -C ${OPT}/libs/d/mir-algorithm-trunk pull -q origin master
fi
fi

install_mir_algorithm() {
    for VERSION in "$@"; do
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

install_mir_algorithm 0.5.17 0.6.13 0.6.21 0.9.5 1.0.0 1.1.0

get_or_sync_git_tag() {
	local DIR=$1
	local URL=$2
	local TAG=$3
	if [ ! -d "${DIR}" ]; then
		git clone -q "${URL}" "${DIR}"
		git -C "${DIR}" checkout -q "${TAG}"
	else
		git -C "${DIR}" reset -q --hard
		git -C "${DIR}" pull -q origin "${TAG}"
	fi
}

get_or_sync_git_tags() {
	local DIR=$1
	local URL=$2
	shift 2
	for TAG in "$@"; do
		get_or_sync_git_tag ${DIR}/${TAG} ${URL} ${TAG}
	done
}

get_or_sync_git_tags libs/ctre https://github.com/hanickadot/compile-time-regular-expressions.git master v2

get_or_sync_git_tags libs/cub https://github.com/NVlabs/cub.git 1.8.0
