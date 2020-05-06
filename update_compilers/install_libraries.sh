#!/bin/bash

# This script installs all the libraries to be used by Compiler Explorer

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. ${SCRIPT_DIR}/common.inc

ARG1="$1"
install_nightly() {
    if [[ "$ARG1" == "nightly" ]]; then
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

update_boost_archive() {
    local NEWEST=$(find "${OPT}/libs" -maxdepth 1 -name 'boost*' -printf '%T@ %p\n' | sort -k1,1nr | head -n1 | cut -d ' ' -f 2)
    if [[ "${NEWEST}" != "${OPT}/libs/boost.tar.xz" ]]; then
        pushd ${OPT}/libs
        rm -rf /tmp/boost.tar.xz
        tar -cJf /tmp/boost.tar.xz boost_*
        mv /tmp/boost.tar.xz boost.tar.xz
        popd
    fi
}

###########################################
# !!!!!!!!!!!!!!! IMPORTANT !!!!!!!!!!!!!!!
###########################################
#
# When adding a new version of boost you must:
#  - run `sudo ~/compiler-explorer-image/update_compilers/install_libraries.sh` on the admin node to generate an updated `${OPT}/libs/boost.tar.xz`
#  - run `make packer` from your own machine to build a new AMI with the new boost version baked in
#  - update the image_id values in `terraform/lc.tf` and commit/push
#  - run `terraform apply` from your own machine so the new images are used when launching new nodes
#  - run `ce --env=prod instances restart` so currently running nodes will rsync the new boost version
#
# This rather convoluted process is required because when new nodes start up they attempt to rsync missing boost versions to a local directory
# and this process can take quite a while, during which compilations using missing boost versions will error out.
# To mitigate this we bake any known boost versions into the AMIs using packer.
#
# See: https://github.com/mattgodbolt/compiler-explorer/issues/1771

install_boost 1.64.0 1.65.0 1.66.0 1.67.0 1.68.0 1.69.0 1.70.0 1.71.0 1.72.0
update_boost_archive

ce_install 'libraries/c++/llvm'

if install_nightly; then
    ce_install 'libraries/c++/nightly'
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
    git -C "${DIR}" submodule sync
    git -C "${DIR}" submodule update --init
}

get_or_sync_git_tag() {
    local DIR=$1
    local URL=$2
    local TAG=$3
    if [[ ! -d "${DIR}" ]]; then
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

get_or_sync libs/cmcstl2 https://github.com/CaseyCarter/cmcstl2.git
get_or_sync libs/GSL https://github.com/Microsoft/GSL.git
get_or_sync libs/gsl-lite https://github.com/martinmoene/gsl-lite.git
get_or_sync libs/opencv https://github.com/opencv/opencv.git
get_or_sync libs/abseil https://github.com/abseil/abseil-cpp.git
get_or_sync libs/cppcoro https://github.com/lewissbaker/cppcoro.git
get_or_sync libs/ctbignum https://github.com/niekbouman/ctbignum.git
get_or_sync libs/outcome https://github.com/ned14/outcome.git
get_or_sync libs/cnl https://github.com/johnmcfarlane/cnl.git
get_or_sync libs/googletest https://github.com/google/googletest.git
get_or_sync libs/tbb https://github.com/01org/tbb.git
get_or_sync libs/nanorange https://github.com/tcbrindle/NanoRange.git
get_or_sync libs/etl https://github.com/ETLCPP/etl.git
get_or_sync libs/NamedType https://github.com/joboccara/NamedType.git

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

get_repo_versioned_and_trunk_with_quirk() {
    local SITE=$1
    local ARCHIVE=$2
    local DIR=$3
    local REPO=$4
    local QUIRK=$5
    local URL=${SITE}/${REPO}

    shift 5
    mkdir -p ${DIR}
    if install_nightly; then
        get_or_sync ${DIR}/${QUIRK}trunk ${URL}.git
    fi
    for tag in "$@"; do
        get_git_version ${DIR}/${QUIRK}${tag} ${URL}/${ARCHIVE}/${tag}.tar.gz
    done
}

get_gitlab_versioned_and_trunk_with_quirk() {
    get_repo_versioned_and_trunk_with_quirk https://gitlab.com -/archive "$@"
}

get_github_versioned_and_trunk_with_quirk() {
    get_repo_versioned_and_trunk_with_quirk https://github.com archive "$@"
}

get_github_versioned_and_trunk() {
    local DIR=$1
    local URL=$2
    shift 2
    get_github_versioned_and_trunk_with_quirk ${DIR} ${URL} '' "$@"
}

ce_install 'libraries/c++/ulib'
ce_install 'libraries/c++/benchmark'

get_github_versioned_and_trunk libs/rangesv3 ericniebler/range-v3 0.3.0 0.3.5 0.3.6 0.4.0 0.9.1 0.10.0
get_github_versioned_and_trunk libs/mp-units mpusz/units v0.3.1 v0.4.0
get_github_versioned_and_trunk libs/dlib davisking/dlib v19.7 v19.9 v19.10
get_github_versioned_and_trunk libs/libguarded copperspice/cs_libguarded libguarded-1.1.0
get_github_versioned_and_trunk libs/brigand edouarda/brigand 1.3.0

ce_install 'libraries/c++/fmt'
ce_install 'libraries/c++/hfsm'
ce_install 'libraries/c++/eigen'
ce_install 'libraries/c++/glm'
ce_install 'libraries/c++/catch2'
ce_install 'libraries/c++/expected-dark'
ce_install 'libraries/c++/expected-lite'
ce_install 'libraries/c++/nlohmann_json'
ce_install 'libraries/c++/tomlplusplus'
ce_install 'libraries/c++/doctest'
get_github_versioned_and_trunk libs/eastl electronicarts/EASTL 3.12.01 3.12.04 3.12.07 3.12.08 3.13.00 3.13.02 3.13.03 3.13.04 3.13.05 3.13.06 3.14.00 3.14.01 3.14.02 3.14.03 3.14.06 3.15.00 3.16.01 3.16.05
ce_install 'libraries/c++/xtl'
ce_install 'libraries/c++/xsimd'
ce_install 'libraries/c++/xtensor'
ce_install 'libraries/c++/seastar'
ce_install 'libraries/c++/PEGTL'
ce_install 'libraries/c++/benri'
ce_install 'libraries/c++/spy'
ce_install 'libraries/c++/hedley'
ce_install 'libraries/c++/GSL'
ce_install 'libraries/c++/vcl'
ce_install 'libraries/c++/blaze'

get_or_sync_git_tags libs/ctre https://github.com/hanickadot/compile-time-regular-expressions.git master v2 ecma-unicode dfa

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

ce_install 'libraries/c++/mir-glas'

if install_nightly; then
    if [ ! -d "${OPT}/libs/d/mir-algorithm-trunk" ]; then
        git clone -q https://github.com/libmir/mir-algorithm.git ${OPT}/libs/d/mir-algorithm-trunk
        git -C ${OPT}/libs/d/mir-algorithm-trunk checkout -q master
    else
        git -C ${OPT}/libs/d/mir-algorithm-trunk pull -q origin master
    fi
fi

ce_install 'libraries/c++/mir-algorithm'

#########################
# CUDA
get_or_sync_git_tags libs/cub https://github.com/NVlabs/cub.git 1.8.0

#########################
# OpenSSL

install_openssl() {
    for VERSION in "$@"; do
        local DEST=${OPT}/libs/openssl/openssl_${VERSION}/x86_64/opt
        if [[ ! -d ${DEST} ]]; then
            rm -rf /tmp/openssl
            mkdir -p /tmp/openssl
            pushd /tmp/openssl
            fetch https://github.com/openssl/openssl/archive/OpenSSL_${VERSION}.tar.gz | tar zxf - --strip-components 1

            setarch i386 ./config -m32 --prefix=${OPT}/libs/openssl/openssl_${VERSION}/x86/opt --openssldir=${OPT}/libs/openssl/openssl_${VERSION}/x86/ssl
            make
            make install
            rm ${OPT}/libs/openssl/openssl_${VERSION}/x86/opt/lib/*.a

            make clean
            ./config --prefix=${OPT}/libs/openssl/openssl_${VERSION}/x86_64/opt --openssldir=${OPT}/libs/openssl/openssl_${VERSION}/x86_64/ssl
            make
            make install
            rm ${OPT}/libs/openssl/openssl_${VERSION}/x86_64/opt/lib/*.a
            popd

            rm -rf /tmp/openssl
        fi
    done
}

install_openssl 1_1_1c

#########################
# cs50

install_cs50_v9() {
    for VERSION in "$@"; do
        local DEST1=${OPT}/libs/cs50/${VERSION}/x86_64/lib
        local DEST2=${OPT}/libs/cs50/${VERSION}/x86/lib
        local INC=${OPT}/libs/cs50/${VERSION}/include
        if [[ ! -d ${DEST1} ]]; then
            rm -rf /tmp/cs50
            mkdir -p /tmp/cs50
            pushd /tmp/cs50
            fetch https://github.com/cs50/libcs50/archive/v${VERSION}.tar.gz | tar zxf - --strip-components 1

            env CFLAGS="-Wall -Wextra -Werror -pedantic -std=c99 -march=native" make -e
            mkdir -p ${DEST1}
            mv build/lib/* ${DEST1}

            mkdir -p ${INC}
            cp -Rf build/include/* ${INC}

            env CFLAGS="-Wall -Wextra -Werror -pedantic -std=c99 -m32" make -e
            mkdir -p ${DEST2}
            mv build/lib/* ${DEST2}

            cd ${DEST1}
            ln -s libcs50.so.${VERSION} libcs50.so.9
            cd ${DEST2}
            ln -s libcs50.so.${VERSION} libcs50.so.9

            popd

            rm -rf /tmp/cs50
        fi
    done
}

install_cs50_v9 9.1.0
