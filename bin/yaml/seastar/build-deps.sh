#!/bin/bash
# Builds Seastar's third-party dependencies as static libraries into PREFIX,
# with the compiler in $CC/$CXX and the flags in $CFLAGS/$CXXFLAGS, so that the
# Seastar library build (libraries.yaml) is self-contained per compiler.
# The builder has none of these as system packages, and CE's hosts don't either,
# so everything a consumer links ends up as a .a in the Seastar package.
#
# Boost and fmt are pinned to versions CE already has on disk
# (/opt/compiler-explorer/libs/boost_1_84_0, libs/fmt/12.0.0), and consumers
# get their headers from there.
#
# Usage: build-deps.sh <prefix>
set -euo pipefail

PREFIX=$1
JOBS=${NUMCPUS:-$(nproc)}
WORK=$(pwd)/seastar-deps-src

: "${CC:?CC must be set}"
: "${CXX:?CXX must be set}"
CFLAGS="${CFLAGS:-} -O2 -fPIC"
CXXFLAGS="${CXXFLAGS:-} -O2 -fPIC"
export CFLAGS CXXFLAGS

AR="ar"
for candidate in "$(dirname "$CC")/ar" "$(dirname "$CC")/llvm-ar"; do
    if [[ -x $candidate ]]; then
        AR=$candidate
        break
    fi
done

mkdir -p "$PREFIX" "$WORK"
cd "$WORK"

# Seastar trunk uses C++23 library features (e.g. std::vector::assign_range) that
# older compilers and standard libraries lack. Fail before spending minutes on
# dependencies that would only feed a doomed Seastar build.
cat >probe.cpp <<'PROBE'
#include <vector>
int main() {
    std::vector<int> v;
    int a[] = {1, 2};
    v.assign_range(a);
    return v.size() == 2 ? 0 : 1;
}
PROBE
# shellcheck disable=SC2086
if ! "$CXX" $CXXFLAGS -std=c++23 -fsyntax-only probe.cpp; then
    echo "$CXX ($CXXFLAGS) lacks the C++23 support Seastar needs, skipping" >&2
    exit 1
fi

fetch() {
    local url=$1 dir=$2
    local archive="$dir.${url##*/}"
    curl -fsSL -o "$archive" "$url"
    mkdir -p "$dir"
    tar xf "$archive" -C "$dir" --strip-components=1
    rm -f "$archive"
}

cmake_dep() {
    local src=$1
    shift
    cmake -S "$src" -B "$src/_build" \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_INSTALL_PREFIX="$PREFIX" \
        -DCMAKE_INSTALL_LIBDIR=lib \
        -DCMAKE_PREFIX_PATH="$PREFIX" \
        -DCMAKE_POSITION_INDEPENDENT_CODE=ON \
        -DBUILD_SHARED_LIBS=OFF \
        -DCMAKE_C_COMPILER="$CC" -DCMAKE_CXX_COMPILER="$CXX" \
        "-DCMAKE_C_FLAGS=$CFLAGS" "-DCMAKE_CXX_FLAGS=$CXXFLAGS" \
        "$@"
    cmake --build "$src/_build" -j "$JOBS"
    cmake --install "$src/_build"
}

# Build-time tools live in $PREFIX/tools; nothing there is needed by consumers.
# The builder has no pkg-config, and Seastar's find modules read dependency
# versions from it.
fetch https://distfiles.ariadne.space/pkgconf/pkgconf-2.3.0.tar.xz pkgconf
(
    cd pkgconf
    ./configure --prefix="$PREFIX/tools" --disable-shared >/dev/null
    make -j "$JOBS" >/dev/null
    make install >/dev/null
    ln -sf pkgconf "$PREFIX/tools/bin/pkg-config"
)

# ragel and protoc are code generators Seastar runs at build time. Give them an
# rpath to the compiler's runtime libraries (libc++, libatomic, ...), which are
# not necessarily on the builder's library path.
TOOL_RPATH=""
for lib in libstdc++.so.6 libgcc_s.so.1 libc++.so.1 libc++abi.so.1 libunwind.so.1 libatomic.so.1; do
    # shellcheck disable=SC2086
    found=$("$CXX" $CXXFLAGS -print-file-name="$lib")
    if [[ $found == /* ]]; then
        TOOL_RPATH="$TOOL_RPATH -Wl,-rpath,$(dirname "$found")"
    fi
done
fetch http://www.colm.net/files/ragel/ragel-6.10.tar.gz ragel
(
    cd ragel
    sed -i "s/ CHAR_M/ SCHAR_M/g" ragel/common.cpp
    ./configure --prefix="$PREFIX/tools" CXXFLAGS="$CXXFLAGS -std=gnu++98" LDFLAGS="${LDFLAGS:-} $TOOL_RPATH" >/dev/null
    make -j "$JOBS" >/dev/null
    make install >/dev/null
)

fetch https://github.com/boostorg/boost/releases/download/boost-1.84.0/boost-1.84.0.tar.xz boost
cmake_dep boost "-DBOOST_INCLUDE_LIBRARIES=program_options;filesystem;thread;test" -DBUILD_TESTING=OFF
# Only the compiled libraries above are built, but Seastar also uses many
# header-only Boost libraries (lockfree, intrusive, ...), so install every header
# for the Seastar build. The library's postbuild_script removes them again.
find boost/libs -type d -path '*/include/boost' -prune -exec cp -r {} "$PREFIX/include/" \;

# Seastar's file.cc needs the xfsprogs ioctl headers (which need libuuid's
# header). They are only needed to build Seastar, so keep them out of include/.
fetch https://mirrors.edge.kernel.org/pub/linux/utils/fs/xfs/xfsprogs/xfsprogs-6.6.0.tar.xz xfsprogs
mkdir -p "$PREFIX/tools/include/xfs" "$PREFIX/tools/include/uuid"
(
    cd xfsprogs
    cp include/{handle,jdm,linux,xfs,xqm,xfs_fs_compat,xfs_arch}.h libxfs/{xfs_fs,xfs_types}.h "$PREFIX/tools/include/xfs/"
)
curl -fsSL -o "$PREFIX/tools/include/uuid/uuid.h" \
    https://raw.githubusercontent.com/util-linux/util-linux/v2.39.3/libuuid/src/uuid.h

fetch https://github.com/fmtlib/fmt/archive/refs/tags/12.0.0.tar.gz fmt
cmake_dep fmt -DFMT_DOC=OFF -DFMT_TEST=OFF

fetch https://github.com/c-ares/c-ares/releases/download/v1.34.5/c-ares-1.34.5.tar.gz c-ares
cmake_dep c-ares -DCARES_STATIC=ON -DCARES_SHARED=OFF -DCARES_BUILD_TOOLS=OFF -DCARES_BUILD_TESTS=OFF

fetch https://github.com/lz4/lz4/releases/download/v1.10.0/lz4-1.10.0.tar.gz lz4
cmake_dep lz4/build/cmake -DLZ4_BUILD_CLI=OFF -DBUILD_STATIC_LIBS=ON

fetch https://github.com/jbeder/yaml-cpp/archive/refs/tags/yaml-cpp-0.9.0.tar.gz yaml-cpp
cmake_dep yaml-cpp -DYAML_CPP_BUILD_TESTS=OFF -DYAML_CPP_BUILD_TOOLS=OFF -DYAML_BUILD_SHARED_LIBS=OFF

# 3.21.x is the last protobuf that does not require abseil.
fetch https://github.com/protocolbuffers/protobuf/releases/download/v21.12/protobuf-cpp-3.21.12.tar.gz protobuf
cmake_dep protobuf -Dprotobuf_BUILD_TESTS=OFF -Dprotobuf_WITH_ZLIB=OFF -Dprotobuf_BUILD_SHARED_LIBS=OFF \
    "-DCMAKE_EXE_LINKER_FLAGS=$TOOL_RPATH"

fetch https://github.com/openssl/openssl/releases/download/openssl-3.5.4/openssl-3.5.4.tar.gz openssl
(
    cd openssl
    ./Configure linux-x86_64 no-shared no-tests no-docs no-apps no-module \
        --prefix="$PREFIX" --libdir=lib >/dev/null
    make -j "$JOBS" >/dev/null
    make install_sw >/dev/null
)

# lksctp-tools only ships an autotools build; libsctp is a handful of C files,
# so compile it directly rather than requiring autoconf on the builder.
fetch https://github.com/sctp/lksctp-tools/archive/refs/tags/v1.0.21.tar.gz lksctp
(
    cd lksctp/src/lib
    mkdir -p "$PREFIX/include/netinet"
    : >config.h
    sed -e 's/@LIBSCTP_.*@//' ../include/netinet/sctp.h.in >"$PREFIX/include/netinet/sctp.h"
    objs=()
    for f in *.c; do
        # shellcheck disable=SC2086
        "$CC" $CFLAGS -I. -I"$PREFIX/include" -c "$f" -o "${f%.c}.o"
        objs+=("${f%.c}.o")
    done
    "$AR" rcs "$PREFIX/lib/libsctp.a" "${objs[@]}"
)

rm -rf "$PREFIX/share/doc" "$PREFIX/share/man"
echo "seastar deps installed into $PREFIX"
