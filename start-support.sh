#!/bin/bash

# designed to be sourced

SKIP_SQUASH=0
CE_USER=ce
ENV=$(cloud-init query userdata)
ENV=${ENV:-prod}
DEPLOY_DIR=${PWD}/.deploy
COMPILERS_FILE=$DEPLOY_DIR/discovered-compilers.json

echo Running in environment "${ENV}"
# shellcheck disable=SC1090
source "${PWD}/site-${ENV}.sh"

get_conf() {
    aws ssm get-parameter --name "$1" | jq -r .Parameter.Value
}

mount_opt() {
    mkdir -p /opt/compiler-explorer
    mountpoint /opt/compiler-explorer || mount --bind /efs/compiler-explorer /opt/compiler-explorer

    mkdir -p /opt/intel
    mountpoint /opt/intel || mount --bind /efs/intel /opt/intel

    mkdir -p /opt/arm
    mountpoint /opt/arm || mount --bind /efs/arm /opt/arm

    mkdir -p /opt/qnx
    mountpoint /opt/qnx || mount --bind /efs/qnx /opt/qnx

    [ -f /opt/.health ] || touch /opt/.health
    mountpoint /opt/.health || mount --bind /efs/.health /opt/.health

    if [[ "${SKIP_SQUASH}" == "0" ]]; then
        # background mounts - serially mounts in the background, in MRU
        ./mount-all-img.sh &

        echo "Done mounting squash images"
    fi
}

get_discovered_compilers() {
    local DEST=$1
    local S3_FILE=$2
    S3_FILE=$(echo "${S3_FILE}" | sed -e 's/.*\/\d*/gh-/g' -e 's/.tar.xz/.json/g')
    local URL=https://s3.amazonaws.com/compiler-explorer/dist/discovery/${BRANCH}/${S3_FILE}
    echo "Discovered compilers from ${URL}"
    curl -sf -o "${COMPILERS_FILE}" "${URL}" || true
}

get_released_code() {
    local DEST=$1
    local S3_KEY=$2
    local URL=https://s3.amazonaws.com/compiler-explorer/${S3_KEY}
    echo "Unpacking build from ${URL}"
    mkdir -p "${DEST}"
    pushd "${DEST}"
    echo "${S3_KEY}" >s3_key
    curl -sL "${URL}" | tar Jxf -
    chown -R ${CE_USER}:${CE_USER} .
    popd
}

update_code() {
    local S3_KEY
    local CUR_S3_KEY=""
    echo "Check to see if CE code needs updating"
    S3_KEY=$(curl -sL "https://s3.amazonaws.com/compiler-explorer/version/${BRANCH}")
    if [[ -f "${DEPLOY_DIR}/s3_key" ]]; then
        CUR_S3_KEY=$(cat "${DEPLOY_DIR}/s3_key")
    fi

    if [[ "${S3_KEY}" == "${CUR_S3_KEY}" ]]; then
        echo "Build ${S3_KEY} already checked out"
    else
        rm -rf "${DEPLOY_DIR}"
        get_released_code "${DEPLOY_DIR}" "${S3_KEY}"
        get_discovered_compilers "${DEPLOY_DIR}" "${S3_KEY}"
    fi
}

install_asmparser() {
    rm -f /usr/local/bin/asm-parser
    cp /opt/compiler-explorer/asm-parser/asm-parser /usr/local/bin
}

install_ninja() {
    rm -f /usr/local/bin/ninja
    cp "$(readlink -f /opt/compiler-explorer/ninja/ninja)" /usr/local/bin
}

setup_cgroups() {
    if grep cgroup2 /proc/filesystems; then
        cgcreate -a ${CE_USER}:${CE_USER} -g memory,pids,cpu:ce-sandbox
        cgcreate -a ${CE_USER}:${CE_USER} -g memory,pids,cpu:ce-compile
        chown ${CE_USER}:root /sys/fs/cgroup/cgroup.procs
    else
        cgcreate -a ${CE_USER}:${CE_USER} -g memory,pids,cpu,net_cls:ce-sandbox
        cgcreate -a ${CE_USER}:${CE_USER} -g memory,pids,cpu,net_cls:ce-compile
    fi
}

mount_nosym() {
    mkdir -p /nosym
    mount -onosymfollow --bind / /nosym
    # seems to need a remount to pick it up properly on our version of Ubuntu (but not 23.10)
    mount -oremount,nosymfollow --bind / /nosym
}
