#!/bin/bash

set -ex

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

if [[ "$1" != "--updated" ]]; then
    git --work-tree ${DIR} pull
    pwd
    exec bash ${BASH_SOURCE[0]} --updated
    exit 0
fi

get_or_update_repo() {
    local USER=$1
    local REPO=$2
    local BRANCH=$3
    local DIR=${4-${REPO}}
    if [[ ! -e ${DIR} ]]; then
        su -c "git clone --branch ${BRANCH} git://github.com/mattgodbolt/${REPO}.git ${DIR}" "${USER}"
    else
        su -c "cd ${DIR}; git pull && git checkout ${BRANCH}" "${USER}"
    fi
}

apt-get -y update
apt-get -y upgrade --force-yes
apt-get -y install git make nodejs-legacy npm docker.io libpng-dev m4

if ! grep ubuntu /etc/passwd; then
    useradd ubuntu
    mkdir /home/ubuntu
    chown ubuntu /home/ubuntu
fi

cd /home/ubuntu/
get_or_update_repo ubuntu jsbeeb release
pushd jsbeeb
su -c "make dist" ubuntu
popd
get_or_update_repo ubuntu jsbeeb master jsbeeb-beta
pushd jsbeeb-beta
su -c "make dist" ubuntu
popd

if ! egrep '^DOCKER_OPTS' /etc/default/docker.io >/dev/null; then
    echo 'DOCKER_OPTS="--restart=false"' >> /etc/default/docker.io
fi
cp /gcc-explorer-image/gcc-explorer.conf /etc/init/
[ "$UPSTART_JOB" != "gcc-explorer" ] && service gcc-explorer start || true
