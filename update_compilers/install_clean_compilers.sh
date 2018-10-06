#!/bin/bash

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
. ${SCRIPT_DIR}/common.inc

get_clean32() {
	local VER=$1
	local VERNODOTS=$2
	local DIR=clean64-$VER

	if [[ ! -d ${DIR} ]]; then
		mkdir ${DIR}
		pushd ${DIR}
		fetch https://ftp.cs.ru.nl/Clean/Clean${VERNODOTS}/linux/clean${VER}_32.tar.gz | tar xzf - --strip-components 1
		popd
	fi
}

get_clean64() {
	local VER=$1
	local VERNODOTS=$2
	local DIR=clean32-$VER

	if [[ ! -d ${DIR} ]]; then
		mkdir ${DIR}
		pushd ${DIR}
		fetch https://ftp.cs.ru.nl/Clean/Clean${VERNODOTS}/linux/clean${VER}_64.tar.gz | tar xzf - --strip-components 1
		popd
	fi
}

get_clean32 2.4 24
get_clean32 3.0 30

get_clean64 2.4 24
get_clean64 3.0 30
