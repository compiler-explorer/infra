#!/bin/bash

# designed to be sourced

SKIP_SQUASH=0
CE_USER=ce

METADATA_TOKEN=$(curl -s -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 21600")
ENV=$(curl -s -H "X-aws-ec2-metadata-token: $METADATA_TOKEN" http://169.254.169.254/latest/meta-data/tags/instance/Environment)
if [ -z "${ENV}" ]; then
    echo "Environment not set!!"
    exit 1
fi
echo Running in environment "${ENV}"

DEPLOY_DIR=${PWD}/.deploy
COMPILERS_FILE=$DEPLOY_DIR/discovered-compilers.json

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
        # don't be tempted to background this, it just causes everything to wedge
        # during startup (startup time I/O etc goes through the roof).
        ./mount-all-img.sh

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

######################
# Debugging a weird apparent race condition at boot that means we don't get the "cpu" delegation
# despite the cgcreates below all succeeding.
# See https://github.com/compiler-explorer/infra/issues/1761
log_cgroups() {
    echo "Cgroup setup diagnostics:"
    echo "Root cgroup.subtree_control: $(cat /sys/fs/cgroup/cgroup.subtree_control)"
    for cgroup in ce-compile ce-sandbox; do
        if [ -d "/sys/fs/cgroup/$cgroup" ]; then
            echo "$cgroup exists: YES"
            echo "  controllers: $(cat /sys/fs/cgroup/$cgroup/cgroup.controllers)"
            echo "  subtree_control: $(cat /sys/fs/cgroup/$cgroup/cgroup.subtree_control)"
            if [ -f "/sys/fs/cgroup/$cgroup/cpu.max" ]; then
                echo "  cpu.max exists: YES"
            else
                echo "  cpu.max exists: NO"
            fi
        else
            echo "$cgroup exists: NO"
        fi
    done
}

setup_cgroups() {
    ######################
    # Debugging a weird apparent race condition at boot that means we don't get the "cpu" delegation
    # despite the cgcreates below all succeeding.
    # See https://github.com/compiler-explorer/infra/issues/1761
    # TODO(mattgodbolt) 2025-08-20 we should no longer need this or log_cgroups. Check for any
    # times we see the "CPU controller missing" message and after a few weeks if no problems,
    # consider removing this complexity.
    echo "Current cgroup.subtree_control: $(cat /sys/fs/cgroup/cgroup.subtree_control)"
    if ! grep -q cpu /sys/fs/cgroup/cgroup.subtree_control; then
        echo "CPU controller missing, adding it"
        echo "+cpu" > /sys/fs/cgroup/cgroup.subtree_control
    fi
    ######################

    if grep cgroup2 /proc/filesystems; then
        cgcreate -a ${CE_USER}:${CE_USER} -g memory,pids,cpu:ce-sandbox
        cgcreate -a ${CE_USER}:${CE_USER} -g memory,pids,cpu:ce-compile
        chown ${CE_USER}:root /sys/fs/cgroup/cgroup.procs
    else
        cgcreate -a ${CE_USER}:${CE_USER} -g memory,pids,cpu,net_cls:ce-sandbox
        cgcreate -a ${CE_USER}:${CE_USER} -g memory,pids,cpu,net_cls:ce-compile
    fi

    ######################
    # Debugging, again see above
    log_cgroups
    ######################
}

mount_nosym() {
    mkdir -p /nosym
    mount -onosymfollow --bind / /nosym
    # seems to need a remount to pick it up properly on our version of Ubuntu (but not 23.10)
    mount -oremount,nosymfollow --bind / /nosym
}

install_ce_router() {
    local latest_version

    latest_version=$(curl -s https://api.github.com/repos/compiler-explorer/ce-router/releases/latest | jq -r '.tag_name')

    if ! curl -sL "https://github.com/compiler-explorer/ce-router/releases/download/${latest_version}/ce-router-${latest_version}.zip" -o /tmp/ce-router.zip; then
        echo "Failed to download ce-router version ${latest_version}"
        return
    fi
    unzip -q -o /tmp/ce-router.zip -d /infra/.deploy
    rm -f /tmp/ce-router.zip
}
