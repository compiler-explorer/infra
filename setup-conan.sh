#!/bin/bash

set -ex

CE_USER=ce
NODE_VERSION="v22.11.0"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${DIR}"

if [[ "$1" != "--updated" ]]; then
    sudo -u ubuntu git -C "${DIR}" pull
    pwd
    exec bash "${BASH_SOURCE[0]}" --updated
    exit 0
fi

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
apt-get -y install unzip wget mosh fish jq ssmtp cronic upx autojump python3-pip python3.8 python3.8-venv sqlite3
apt-get -y autoremove
pip3 install --upgrade pip
hash -r pip3
pip3 install --upgrade awscli

# setup ce_user
adduser --system --group ${CE_USER}

mkdir -p /home/${CE_USER}/.conan_server
echo "/dev/data/datavol       /home/${CE_USER}/.conan_server   ext4   defaults,user=${CE_USER}       0 0
" >>/etc/fstab

# note: dont mount yet, volume will not be available

# setup latest conan-server
sudo -u ${CE_USER} -H pip3 install conan gunicorn

# setup conanproxy
mkdir -p /home/ubuntu/ceconan
cd /home/ubuntu/ceconan
git clone https://github.com/compiler-explorer/conanproxy.git

# setup node
cd /home/ubuntu

rm -Rf node
wget https://nodejs.org/dist/${NODE_VERSION}/node-${NODE_VERSION}-linux-x64.tar.xz
tar -xf node-${NODE_VERSION}-linux-x64.tar.xz
mv node-${NODE_VERSION}-linux-x64 node
chown -Rf root:root node

# quick smoke test of this node version
node/bin/node --version

# setup daemon
cp /home/ubuntu/infra/init/ce-conan.service /lib/systemd/system/ce-conan.service
systemctl daemon-reload
systemctl enable ce-conan


# setup logging
mkdir -p /root/.aws /home/ubuntu/.aws
echo -e "[default]\nregion=us-east-1" | tee /root/.aws/config /home/ubuntu/.aws/config
chown -R ubuntu /home/ubuntu/.aws

get_conf() {
    aws ssm get-parameter --name "$1" | jq -r .Parameter.Value
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

# ---

cd /home/ubuntu/

mkdir -p /home/ubuntu/.ssh
mkdir -p /tmp/auth_keys
aws s3 sync s3://compiler-explorer/authorized_keys /tmp/auth_keys
cat /tmp/auth_keys/* >>/home/ubuntu/.ssh/authorized_keys
rm -rf /tmp/auth_keys
chown -R ubuntu /home/ubuntu/.ssh


# Install private and public keys
aws ssm get-parameter --name /admin/ce_private_key | jq -r .Parameter.Value >/home/ubuntu/.ssh/id_rsa

chmod 600 /home/ubuntu/.ssh/id_rsa
aws s3 cp s3://compiler-explorer/authorized_keys/admin.key /home/ubuntu/.ssh/id_rsa.pub
chown -R ubuntu:ubuntu /home/ubuntu/.ssh
chown -R ubuntu:ubuntu /home/ubuntu/infra

echo conan-node > /etc/hostname
hostname conan-node
sed -i "/127.0.0.1/c 127.0.0.1 localhost conan-node" /etc/hosts
sed -i "/preserve_hostname/c preserve_hostname: true" /etc/cloud/cloud.cfg
