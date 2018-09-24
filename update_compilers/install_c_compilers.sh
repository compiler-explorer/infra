#!/bin/bash

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
. ${SCRIPT_DIR}/common.inc


install_nightly() {
    if [[ "$ARG1" = "nightly" ]]; then
        return 0
    else
        return 1
    fi
}

get_ppci() {
  local VER=$1
  local DIR=ppci-$VER

  if [[ ! -d ${DIR} ]]; then
    fetch https://pypi.io/packages/source/p/ppci/ppci-$VER.tar.gz | tar xfz -
  fi
}

get_ppci 0.5.5
