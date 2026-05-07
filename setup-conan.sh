#!/bin/bash

set -ex

CE_USER=ce
# Match the legacy bionic conan-node's ce uid/gid (`id ce` -> uid=111(ce) gid=115(ce))
# so files on the reattached data volume keep their owner and no chown is needed
# on cutover or rollback. If these ever diverge from /etc/passwd on the live host,
# update them before baking; a mismatch turns rollback into a recursive chown.
CE_UID=111
CE_GID=115
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
apt-get -y upgrade
apt-get -y install \
    unzip wget mosh fish jq ssmtp cronic upx \
    python3-pip python3-venv \
    sqlite3 \
    lvm2 rsyslog
apt-get -y autoremove

# Install AWS CLI v2 (system pip is PEP 668-restricted on noble)
pushd /tmp
curl -sL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip -q awscliv2.zip
./aws/install
rm -rf aws awscliv2.zip
popd

# Create ce group/user with the legacy uid/gid; explicit --home because adduser
# --system defaults to /nonexistent on noble, which would break the venv below.
groupadd --system --gid "${CE_GID}" "${CE_USER}"
useradd --system --uid "${CE_UID}" --gid "${CE_GID}" \
    --home-dir "/home/${CE_USER}" --shell /usr/sbin/nologin "${CE_USER}"
mkdir -p /home/${CE_USER}/.conan_server
chown -R ${CE_USER}:${CE_USER} /home/${CE_USER}

# Data volume is LVM (created on the legacy bionic instance). Mounted at first boot
# from the existing /etc/fstab below; do not mount during AMI bake — the volume
# will not be present.
echo "/dev/data/datavol       /home/${CE_USER}/.conan_server   ext4   defaults,user=${CE_USER}       0 0
" >>/etc/fstab

# setup conan-server in a venv. Pinned to 1.66.0 (the last v1 release).
# Builders run conan==1.59 (init/start-builder.sh:35), but 1.59 transitively
# pins PyYAML<=6.0, which has no Python 3.12 wheel and fails to build from
# source against modern Cython ('build_ext' has no attribute 'cython_sources').
# 1.66 relaxes the PyYAML pin and installs cleanly. v1 wire protocol is stable
# across the 1.x series, so 1.66 server <-> 1.59 client is fine. v2 would be a
# hard break.
sudo -u ${CE_USER} -H python3 -m venv /home/${CE_USER}/venv
sudo -u ${CE_USER} -H /home/${CE_USER}/venv/bin/pip install 'conan==1.66.0' gunicorn

# Make /home/ubuntu world-traversable so the ce user can reach conanproxy and
# the node binary at runtime. Noble defaults adduser HOME_MODE to 0750; bionic
# was 0755, which is what start-conan.sh's `sudo -u ce -H /home/ubuntu/...`
# silently relied on.
chmod 755 /home/ubuntu

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
curl -sL 'https://github.com/papertrail/remote_syslog2/releases/download/v0.21/remote_syslog_linux_amd64.tar.gz' | tar zxf -
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

# Install grafana-agent. Conan-node has a real data mount at
# /home/ce/.conan_server, so override FS_IGNORE to let it through. We'd
# rather express this as an allowlist ('only / and /home/ce/.conan_server')
# but grafana-agent's node_exporter integration only exposes the deny side
# (filesystem_mount_points_exclude). The denylist below covers every mount
# type we know to be noisy or high-cardinality (kernel, tmpfs, snap, EFS,
# CEFS, docker), so if we ever add anything fundamentally new -- a different
# autofs, a sidecar container's overlay -- update this regex before the
# Grafana Cloud bill notices.
FS_IGNORE='^/(dev|proc|sys|run|tmp|snap|boot|cefs|efs|var/lib/(docker|snapd))($|/)' /home/ubuntu/infra/grafana/install-agent.sh

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
