#!/bin/bash

set -ex

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

if [[ ! -f /updated ]]; then
    apt-get -y update
    apt-get -y upgrade --force-yes
    apt-get -y install unzip libwww-perl libdatetime-perl nfs-common jq python-pip wget cachefilesd
    apt-get -y autoremove
    pip install --upgrade pip
    pip install --upgrade awscli
    wget -qO- https://get.docker.com/ | sh
    touch /updated
fi

if [[ ! -f /root/.aws ]]; then
    mkdir -p /root/.aws /home/ubuntu/.aws
    echo -e "[default]\nregion=us-east-1" | tee /root/.aws/config /home/ubuntu/.aws/config
    chown -R ubuntu /home/ubuntu/.aws
fi

if [[ ! -f /updated2 ]]; then
    # TODO fold in with the above
    rm -rf /tmp/acwa
    mkdir -p /tmp/acwa
    curl -sL https://s3.amazonaws.com/amazoncloudwatch-agent/linux/amd64/latest/AmazonCloudWatchAgent.zip -o /tmp/acwa/acwa.zip
    pushd /tmp/acwa
    unzip acwa.zip
    rm acwa.zip
    ./install.sh
    popd
    rm -rf /tmp/acwa
    /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl -a fetch-config -m ec2 -c ssm:agent-config-linux -s
    touch /updated2
fi


get_conf() {
    aws ssm get-parameter --name $1 | jq -r .Parameter.Value
}

if [[ -f /etc/newrelic-infra.yml ]]; then
   apt-get remove -y newrelic-infra
fi

PTRAIL='/etc/rsyslog.d/99-papertrail.conf'
if [[ ! -f "${PTRAIL}" ]]; then
    echo '*.*          @logs2.papertrailapp.com:34474' > "${PTRAIL}"
    service rsyslog restart
    pushd /tmp
    curl -sL 'https://github.com/papertrail/remote_syslog2/releases/download/v0.17/remote_syslog_linux_amd64.tar.gz' | tar zxf -
    cp remote_syslog/remote_syslog /usr/local/bin/
    docker pull gliderlabs/logspout:latest
    popd
fi

killall remote_syslog || true
cat > /etc/log_files.yml << EOF
files:
    - /var/log/nginx/xania.*
destination:
    host: logs2.papertrailapp.com
    port: 34474
    protocol: tls
EOF
remote_syslog

docker stop logspout || true
docker rm logspout || true
docker run --name logspout -d -v=/var/run/docker.sock:/tmp/docker.sock -h $(hostname) gliderlabs/logspout syslog://logs2.papertrailapp.com:34474

mountpoint -q /opt || mount -t nfs4 -o nfsvers=4.1,rsize=1048576,wsize=1048576,hard,timeo=600,retrans=2,noatime,nodiratime,nocto${EXTRA_NFS_ARGS} $(curl -s http://169.254.169.254/latest/meta-data/placement/availability-zone).fs-db4c8192.efs.us-east-1.amazonaws.com:/ /opt

cd /home/ubuntu/

mkdir -p /home/ubuntu/.ssh
mkdir -p /tmp/auth_keys
aws s3 sync s3://compiler-explorer/authorized_keys /tmp/auth_keys
cat /tmp/auth_keys/* >> /home/ubuntu/.ssh/authorized_keys
rm -rf /tmp/auth_keys
chown -R ubuntu /home/ubuntu/.ssh

if ! egrep '^DOCKER_OPTS' /etc/default/docker.io >/dev/null; then
    echo 'DOCKER_OPTS="--restart=false"' >> /etc/default/docker.io
fi
