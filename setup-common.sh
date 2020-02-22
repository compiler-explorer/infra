#!/bin/bash

set -ex

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# https://askubuntu.com/questions/132059/how-to-make-a-package-manager-wait-if-another-instance-of-apt-is-running
wait_for_apt() {
    while fuser /var/lib/dpkg/lock >/dev/null 2>&1; do
        echo "Waiting for other software managers to finish..."
        sleep 5
    done
}

# Sometimes it seems auto apt takes a while to kick in...
sleep 5
wait_for_apt
sleep 5
wait_for_apt

apt-get -y update
apt-get -y upgrade --force-yes
apt-get -y install unzip libwww-perl libdatetime-perl nfs-common jq python-pip wget cachefilesd qemu-user-static libc6-arm64-cross
apt-get -y autoremove
pip install --upgrade pip
hash -r pip
pip install --upgrade awscli
touch /updated

mkdir -p /root/.aws /home/ubuntu/.aws
echo -e "[default]\nregion=us-east-1" | tee /root/.aws/config /home/ubuntu/.aws/config
chown -R ubuntu /home/ubuntu/.aws

get_conf() {
    aws ssm get-parameter --name $1 | jq -r .Parameter.Value
}

LOG_DEST_HOST=$(get_conf /compiler-explorer/logDestHost)
LOG_DEST_PORT=$(get_conf /compiler-explorer/logDestPort)
PTRAIL='/etc/rsyslog.d/99-papertrail.conf'
echo "*.*          @${LOG_DEST_HOST}:${LOG_DEST_PORT}" >"${PTRAIL}"
service rsyslog restart
pushd /tmp
curl -sL 'https://github.com/papertrail/remote_syslog2/releases/download/v0.20/remote_syslog_linux_amd64.tar.gz' | tar zxf -
cp remote_syslog/remote_syslog /usr/local/bin/
popd

cat >/etc/log_files.yml <<EOF
files:
    - /var/log/nginx/*.err
destination:
    host: ${LOG_DEST_HOST}
    port: ${LOG_DEST_PORT}
    protocol: tls
EOF

cat >/lib/systemd/system/remote-syslog.service <<EOF
[Unit]
Description=remote_syslog2
Documentation=https://github.com/papertrail/remote_syslog2
After=network-online.target

[Service]
ExecStartPre=/usr/bin/test -e /etc/log_files.yml
ExecStart=/usr/local/bin/remote_syslog -D
Restart=always
User=root
Group=root

[Install]
WantedBy=multi-user.target
EOF
systemctl enable remote-syslog

mkdir -p /efs
if ! grep "/efs nfs" /etc/fstab; then
    echo "fs-db4c8192.efs.us-east-1.amazonaws.com:/ /efs nfs nfsvers=4.1,rsize=1048576,wsize=1048576,hard,timeo=600,retrans=2,noresvport${EXTRA_NFS_ARGS} 0 0" >>/etc/fstab
fi

mount -a

cd /home/ubuntu/

mkdir -p /home/ubuntu/.ssh
mkdir -p /tmp/auth_keys
aws s3 sync s3://compiler-explorer/authorized_keys /tmp/auth_keys
cat /tmp/auth_keys/* >>/home/ubuntu/.ssh/authorized_keys
rm -rf /tmp/auth_keys
chown -R ubuntu /home/ubuntu/.ssh
