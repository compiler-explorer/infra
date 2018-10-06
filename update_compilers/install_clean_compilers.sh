#!/bin/bash

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
. ${SCRIPT_DIR}/common.inc

get_clean() {
	local VER=$1
	local VERNODOTS=$2
	local DIR=clean-$VER

	if [[ ! -d ${DIR} ]]; then
		mkdir ${DIR}
		pushd ${DIR}
		fetch https://ftp.cs.ru.nl/Clean/Clean${VERNODOTS}/linux/clean${VER}_64.tar.gz | tar xzf - --strip-components 1
		popd
	fi
}

get_clean 2.4 24
get_clean 3.0 30

