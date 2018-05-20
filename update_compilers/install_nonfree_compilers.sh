#!/usr/bin/env bash

# This script installs all the non-free compilers from s3 into a dir in /opt.
# On EC2 this location is on an EFS drive.

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
. ${DIR}/common.inc
S3URL=s3://compiler-explorer/opt-nonfree

##################################
# Intel compilers
for compiler in \
    intel.tar.gz
do
    DIR=${compiler%.tar.*}
	if [[ ! -d ${DIR} ]]; then
		s3get ${S3URL}/$compiler ${OPT}/$compiler
		tar zxf $compiler
		rm $compiler
		do_strip ${DIR}
	fi
done

for license in COM_L__CPPFOR_HFGW-87P5C9BZ.lic NCOM_L__CPPFOR_ND83-JL4ZKB6T.lic; do
	s3get ${S3URL}/$license ${OPT}/intel/licenses
done

for version in 2016.3.210 2018.0.033; do
    if [[ ! -d intel-${version} ]]; then
        compiler=intel-${version}.tar.xz
        s3get ${S3URL}/$compiler ${OPT}/$compiler
        tar axf $compiler
        rm $compiler
    fi
done

# Workaround for Intel license
for license_dir in \
    composer_xe_2013.1.117 \
    intel-2018.0.033/compilers_and_libraries_2018.0.128/linux \
; do
    mkdir -p ${license_dir}/Licenses
    cp ${OPT}/intel/licenses/* ${OPT}/${license_dir}/Licenses/
done


##################################
# Windows compilers
fix_up_windows() {
    local file=$1
    if [[ -d ${file}/lib/native/bin/amd64 ]]; then
        cp ${file}/lib/native/bin/amd64/mspdb140.dll ${file}/lib/native/bin/amd64_arm/
        cp ${file}/lib/native/bin/amd64/msvcdis140.dll ${file}/lib/native/bin/amd64_arm/
        cp ${file}/lib/native/bin/amd64/mspdb140.dll ${file}/lib/native/bin/amd64_x86/
    fi
}

mkdir -p windows
pushd windows
for file in \
    10.0.10240.0 \
    14.0.24224-Pre \
    19.10.25017 \
; do
    if [[ ! -d ${file} ]]; then
        s3get ${S3URL}/${file}.tar.xz ${file}.tar.xz
        tar Jxf ${file}.tar.xz
        fix_up_windows ${file}
        rm ${file}.tar.xz
    fi
done

for file in \
    14.0.24629 \
; do
    if [[ ! -d ${file} ]]; then
        mkdir ${file}
        pushd ${file}
        fetch http://vcppdogfooding.azurewebsites.net/api/v2/package/visualcpptools/${file} > ${file}.zip
        do_unzip ${file}.zip
        rm ${file}.zip
        popd
        fix_up_windows ${file}
    fi
done
popd

##################################
# Zapcc
for version in 20170226-190308-1.0; do
    fullname=zapcc-${version}
    if [[ ! -d ${fullname} ]]; then
        compiler=${fullname}.tar.gz
        s3get ${S3URL}/${compiler} ${OPT}/$compiler
        tar axf $compiler
        rm $compiler
        s3get ${S3URL}/zapcc-key.txt ${OPT}/${fullname}/bin/zapcc-key.txt
    fi
done

##################################
# CUDA
install_cuda() {
    local URL=$1
    mkdir -p cuda
    pushd cuda
    local DIR=$(pwd)/$2
    if [[ ! -d ${DIR} ]]; then
      rm -rf /tmp/cuda
      mkdir /tmp/cuda
      fetch ${URL} > /tmp/cuda/combined.sh
      sh /tmp/cuda/combined.sh --extract=/tmp/cuda
      local LINUX=$(ls -1 /tmp/cuda/cuda-linux.$2*.run)
      ${LINUX} --prefix=${DIR} -noprompt -nosymlink -no-man-page
      rm -rf /tmp/cuda
    fi
    popd
}

install_cuda https://developer.nvidia.com/compute/cuda/9.1/Prod/local_installers/cuda_9.1.85_387.26_linux 9.1.85
install_cuda https://developer.nvidia.com/compute/cuda/9.2/Prod/local_installers/cuda_9.2.88_396.26_linux 9.2.88
