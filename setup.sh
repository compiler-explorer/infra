#!/bin/bash

set -ex

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

if [[ "$1" != "--updated" ]]; then
    git --work-tree ${DIR} pull
    pwd
    exec bash ${BASH_SOURCE[0]} --updated
    exit 0
fi

miraclehook() {
    mkdir -p roms
    pushd roms
    wget -O mycreds -q 'http://169.254.169.254/latest/meta-data/iam/security-credentials/myrole'
    SECRET_KEY=$(jq -r '.SecretAccessKey' mycreds)
    ACCESS_KEY=$(jq -r '.AccessKeyId' mycreds)
    TOKEN=$(jq -r '.Token' <mycreds)
    cat >s3cfg <<EOF
[default]
access_key = $ACCESS_KEY
secret_key = $SECRET_KEY
security_token = $TOKEN
EOF
    s3cmd --config s3cfg get s3://xania.org/miracle-roms.tar.gz
    tar zxf miracle-roms.tar.gz
    rm miracle-roms.tar.gz s3cfg
    popd
}

get_or_update_repo() {
    local USER=$1
    local REPO=$2
    local BRANCH=$3
    local DIR=$4
    if [[ ! -e ${DIR} ]]; then
        su -c "git clone --branch ${BRANCH} ${REPO} ${DIR}" "${USER}"
    else
        su -c "cd ${DIR}; git pull && git checkout ${BRANCH}" "${USER}"
    fi
    pushd ${DIR}
    $5
    su -c "make dist" ${USER}
    popd
}

apt-get -y update
apt-get -y upgrade --force-yes
apt-get -y install git make nodejs-legacy npm docker.io libpng-dev m4 \
    python-markdown python-pygments python-pip perl jq s3cmd
pip install pytz

if ! grep ubuntu /etc/passwd; then
    useradd ubuntu
    mkdir /home/ubuntu
    chown ubuntu /home/ubuntu
fi

mkdir -p /home/ubuntu/.ssh
cp /root/.ssh/known_hosts /root/.ssh/id_rsa* /home/ubuntu/.ssh/
chown -R ubuntu /home/ubuntu/.ssh
chmod 600 /home/ubuntu/.ssh/id_rsa

cd /home/ubuntu/
get_or_update_repo ubuntu git://github.com/mattgodbolt/jsbeeb.git release jsbeeb
get_or_update_repo ubuntu git://github.com/mattgodbolt/jsbeeb.git master jsbeeb-beta
get_or_update_repo ubuntu git://github.com/mattgodbolt/Miracle master miracle miraclehook
get_or_update_repo ubuntu git@github.com:mattgodbolt/blog.git master blog

if ! egrep '^DOCKER_OPTS' /etc/default/docker.io >/dev/null; then
    echo 'DOCKER_OPTS="--restart=false"' >> /etc/default/docker.io
fi
cp /gcc-explorer-image/gcc-explorer.conf /etc/init/
[ "$UPSTART_JOB" != "gcc-explorer" ] && service gcc-explorer start || true
