#!/bin/bash

set -ex

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

if [[ "$1" != "--updated" ]]; then
    git --work-tree ${DIR} pull
    pwd
    exec bash ${BASH_SOURCE[0]} --updated
    exit 0
fi

if [[ ! -f /updated ]]; then
    apt-get -y update
    apt-get -y upgrade --force-yes
    apt-get -y install unzip libwww-perl libdatetime-perl nfs-common
    curl -sL http://aws-cloudwatch.s3.amazonaws.com/downloads/CloudWatchMonitoringScripts-1.2.1.zip -o /tmp/cwm.zip
    cd /root
    unzip /tmp/cwm.zip
    rm /tmp/cwm.zip
    echo '*/5 * * * * root /root/aws-scripts-mon/mon-put-instance-data.pl ' \
         '--mem-util --disk-space-util --disk-path=/ --auto-scaling --from-cron' >> /etc/crontab
    touch /updated
fi

if ! grep ubuntu /etc/passwd; then
    useradd ubuntu
    mkdir /home/ubuntu
    chown ubuntu /home/ubuntu
fi

if ! which docker 2>&1 > /dev/null; then
    apt-get -y install wget
    wget -qO- https://get.docker.com/ | sh
fi

if ! which aws 2>&1 > /dev/null; then
    apt-get -y install awscli
    mkdir -p /root/.aws /home/ubuntu/.aws
    echo -e "[default]\nregion=us-east-1" | tee /root/.aws/config /home/ubuntu/.aws/config
    chown -R ubuntu /home/ubuntu/.aws
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

# TODO ideally we would mount this readonly but the rsync operation to the versioned directory requires it :/
apt-get install cachefilesd
/etc/init.d/cachefilesd stop
echo 'RUN="yes"' >> /etc/default/cachefilesd
/etc/init.d/cachefilesd start
mountpoint -q /opt || mount -t nfs4 -o nfsvers=4.1,fsc $(curl -s http://169.254.169.254/latest/meta-data/placement/availability-zone).fs-db4c8192.efs.us-east-1.amazonaws.com:/ /opt &

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
cp /compiler-explorer-image/init/compiler-explorer.service /lib/systemd/system/compiler-explorer.service
systemctl daemon-reload
systemctl enable compiler-explorer

wait # wait for mount point

[ -n "$PACKER_SETUP" ] && exit

docker pull -a mattgodbolt/compiler-explorer
docker pull nginx
