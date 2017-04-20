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

# Workaround for Intel license
mkdir -p ${OPT}/composer_xe_2013.1.117/Licenses/
cp ${OPT}/intel/licenses/* ${OPT}/composer_xe_2013.1.117/Licenses/

# ICCs also UPX'd
for version in 2016.3.210; do
    if [[ ! -d intel-${version} ]]; then
        compiler=intel-${version}.tar.xz
        s3get ${S3URL}/$compiler ${OPT}/$compiler
        tar axf $compiler
        rm $compiler
    fi
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
