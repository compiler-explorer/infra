#!/bin/bash

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
. ${SCRIPT_DIR}/common.inc

get_clean24() {
	local VER=$1
	local DIR=clean-$VER

	if [[ ! -d ${DIR} ]]; then
		mkdir ${DIR}
		pushd ${DIR}
		fetch http://clean.cs.ru.nl/download/Clean24/linux/clean${VER}_64.tar.gz | tar xzf - --strip-components 1
		popd
	fi
}

get_clean24 2.4

