#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "${SCRIPT_DIR}"/common.inc

# Some things need to be installed in `/opt/arm` so they can be kept out of the execution path.
ARM_ROOT=/opt/arm
mkdir -p ${ARM_ROOT}

##################################
# Linaro AArch64 sysroot
#
# This is needed for system libraries, in order to build aarch64 binaries on
# x86_64
#
install_linaro_aarch64_sysroot() {
    local LINARO_URL=$1
    local DIR=${OPT}/aarch64-sysroot-$2
    if [[ -d "${DIR}" ]]; then
        return
    fi
    mkdir -p "${DIR}"
    fetch "${LINARO_URL}" | tar -xJf - --strip-components 1 -C "${DIR}"
}

install_linaro_aarch64_sysroot https://releases.linaro.org/components/toolchain/binaries/latest-7/aarch64-linux-gnu/sysroot-glibc-linaro-2.25-2019.02-aarch64-linux-gnu.tar.xz 2019.02

##################################
# Arm Compiler for Linux
#
install_arm() {
    local ARMCLANG_S3_URL=$1
    local VERSION=$2
    local DIR=${ARM_ROOT}/${VERSION}
    if [[ -d ${DIR} ]]; then
        return
    fi
    local TEMP_DIR=${DIR}-temp
    rm -rf "${TEMP_DIR}"
    mkdir -p "${TEMP_DIR}"
    rm -rf /tmp/arm-install
    mkdir /tmp/arm-install
    pushd /tmp/arm-install || exit 1
    s3get "${ARMCLANG_S3_URL}" arm.tar
    tar xf arm.tar
    rm arm.tar
    bash ./ARM-Compiler*/*.sh --accept --save-packages-to packages
    local PACKAGE_DIR UARCH COMPILER PACKAGE_NAME CTRL SUMS
    declare -A PACKAGE_DIRS
    for package in packages/*.deb; do
        ar p "$package" data.tar.bz2 | tar jxvf - --strip-components 3 -C "${TEMP_DIR}" ./opt/arm/
        mkdir -p $package-control
        ar p "$package" control.tar.gz | tar zxvf - -C $package-control
        CTRL="$package-control/control"
        SUMS="$package-control/md5sums"
        PACKAGE_NAME=$(grep '^Package: ' "${CTRL}" | cut -d\  -f2-)
        PACKAGE_DIR=$(grep -m1 'opt/arm' "${SUMS}" | cut -d/ -f3)
        PACKAGE_DIRS[$PACKAGE_NAME]="$PACKAGE_DIR"
    done

    for package in packages/*.deb; do
        if [[ -x "$package-control/postinst" ]]; then
            CTRL="$package-control/control"
            UARCH=$(grep '^Microarch: ' "${CTRL}" | cut -d\  -f2- | tr A-Z a-z)
            COMPILER=$(grep '^Depends: ' "${CTRL}" | cut -d\  -f2- | cut -d, -f1)
            PACKAGE_NAME=$(grep '^Package: ' "${CTRL}" | cut -d\  -f2-)
            "$package-control/postinst" \
                --force-compiler-location "${TEMP_DIR}/${PACKAGE_DIRS[$COMPILER]}" \
                --force-libraries-location "${TEMP_DIR}/${PACKAGE_DIRS[$PACKAGE_NAME]}" \
                --force-uarch $UARCH
        fi
    done
    rm -rf /tmp/arm-install
    popd || exit 1
    mv "${TEMP_DIR}" "${DIR}"
}

install_arm s3://compiler-explorer/opt-nonfree/Arm-Compiler-for-HPC_19.3_Ubuntu_16.04_aarch64.tar 19.3

##################################
# Arm Compiler for Linux wrapper script
#
# Creates three wrappers (armclang-wrapper, armclang++-wrapper,
# armflang-wrapper), which set up a number of environment variables, then call
# the real binary using user-space qemu
#
install_arm_wrapper() {
    local COMPILER_DIR=$1
    local GCC_TOOLCHAIN=$2
    local CLANG_RESOURCE_DIR=$3
    local BUILD_NUM=$4
    local SYSROOT=$5
    for compiler in \
        armclang \
        armclang++ \
        armflang; do
        local WRAPPER="$COMPILER_DIR"/bin/${compiler}-wrapper
        cat <<EOF >"$WRAPPER"
#!/bin/bash
# Auto-generated wrapper, to allow Arm Compiler to execute without loading
# its environment module (found in ${COMPILER_DIR}/modulefiles)
export ARM_HPC_COMPILER_DIR=${COMPILER_DIR}
export ARM_HPC_COMPILER_BUILD=${BUILD_NUM}
export ARM_HPC_COMPILER_INCLUDES=\${ARM_HPC_COMPILER_DIR}/include
export ARM_HPC_COMPILER_LIBRARIES=\${ARM_HPC_COMPILER_DIR}/lib
export ARM_HPC_COMPILER_LICENSE_SEARCH_PATH=/opt/arm/licences:/opt/arm/licenses
export PATH=\${ARM_HPC_COMPILER_DIR}/bin:$PATH
export CPATH=\${ARM_HPC_COMPILER_INCLUDES}:$CPATH
export LD_LIBRARY_PATH=\${ARM_HPC_COMPILER_LIBRARIES}:${LD_LIBRARY_PATH}
export LIBRARY_PATH=\${ARM_HPC_COMPILER_LIBRARIES}:${LIBRARY_PATH}
export MANPATH=\${ARM_HPC_COMPILER_DIR}/share/man:$MANPATH
export LD_LIBRARY_PATH=\${ARM_HPC_COMPILER_DIR}/${CLANG_RESOURCE_DIR}/armpl_links/lib:${LD_LIBRARY_PATH}
export QEMU_LD_PREFIX=/usr/aarch64-linux-gnu
qemu-aarch64-static -L $SYSROOT \${ARM_HPC_COMPILER_DIR}/bin/${compiler} --sysroot=$SYSROOT --gcc-toolchain=$GCC_TOOLCHAIN \$*
EOF
        chmod +x "${WRAPPER}"
    done
}

# TODO ideally this wouldn't have to be so highly specified
install_arm_wrapper /opt/arm/19.3/arm-hpc-compiler-19.3_Generic-AArch64_Ubuntu-16.04_aarch64-linux \
    /opt/arm/19.3/gcc-8.2.0_Generic-AArch64_Ubuntu-16.04_aarch64-linux \
    lib/clang/7.1.0 \
    61 \
    /opt/compiler-explorer/aarch64-sysroot-2019.02
