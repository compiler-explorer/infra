#!/bin/bash

set -exuo pipefail

INSTALL_TYPE=${1:-non-ci}

# Disable automatic updates etc
systemctl stop apt-daily{,-upgrade}.{service,timer} unattended-upgrades.service
systemctl disable apt-daily{,-upgrade}.{service,timer} unattended-upgrades.service

# Disable installing recommended packages by default
echo 'APT::Install-Recommends "false";' > /etc/apt/apt.conf.d/99-no-install-recommends

# Disable unattended upgrades
apt purge -y --auto-remove unattended-upgrades

apt-get -y update
apt-get -y dist-upgrade --force-yes

apt-get -y install \
  autofs \
  gpg-agent \
  jq \
  locales \
  libc6-arm64-cross \
  libdatetime-perl \
  libtinfo\* \
  libwww-perl \
  nfs-common \
  python-is-python3 \
  python3-pip \
  python3-venv \
  qemu-user-static \
  rsyslog \
  ssmtp \
  unzip \
  wget

locale-gen en_US.UTF-8

apt-get autoremove --purge -y

# This returns amd64 or arm64
ARCH=$(dpkg --print-architecture)

if [ "$INSTALL_TYPE" != 'ci' ]; then
  mkdir /tmp/aws-install
  pushd /tmp/aws-install
  if [ "$ARCH" == 'amd64' ]; then
    curl -sL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
  else
    curl -sL "https://awscli.amazonaws.com/awscli-exe-linux-aarch64.zip" -o "awscliv2.zip"
  fi
  unzip awscliv2.zip
  ./aws/install
  popd
  rm -rf /tmp/aws-install
fi

mkdir -p /root/.aws /home/ubuntu/.aws
echo -e "[default]\nregion=us-east-1" | tee /root/.aws/config /home/ubuntu/.aws/config
chown -R ubuntu /home/ubuntu/.aws

get_conf() {
  aws ssm get-parameter --name "$1" | jq -r .Parameter.Value
}

# Allow override of SSM parameter paths for log destination
LOG_DEST_HOST_PARAM="${LOG_DEST_HOST_PARAM:-/compiler-explorer/logDestHost}"
LOG_DEST_PORT_PARAM="${LOG_DEST_PORT_PARAM:-/compiler-explorer/logDestPort}"

LOG_DEST_HOST=$(get_conf "${LOG_DEST_HOST_PARAM}")
LOG_DEST_PORT=$(get_conf "${LOG_DEST_PORT_PARAM}")
PTRAIL='/etc/rsyslog.d/99-papertrail.conf'
echo "*.*          @${LOG_DEST_HOST}:${LOG_DEST_PORT}" >"${PTRAIL}"
service rsyslog restart
pushd /tmp

if [ "$ARCH" == 'amd64' ]; then
  curl -sL 'https://github.com/papertrail/remote_syslog2/releases/download/v0.21/remote_syslog_linux_amd64.tar.gz' | tar zxf -
else
  curl -sL 'https://github.com/papertrail/remote_syslog2/releases/download/v0.21/remote_syslog_linux_arm64.tar.gz' | tar zxf -
fi

cp remote_syslog/remote_syslog /usr/local/bin/
popd

cat >/etc/log_files.yml <<EOF
files:
    - /var/log/nginx/*.err
exclude_patterns:
    - smbd_calculate_access_mask_fsp
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

cp /infra/init/log-instance-id.service /lib/systemd/system/log-instance-id.service
systemctl enable log-instance-id

setup_grafana() {
    local GRAFANA_CONFIG=/infra/grafana/agent.yaml
    local GRAFANA_VERSION=0.41.1

    pushd /tmp
    curl -sLo agent-linux.zip "https://github.com/grafana/agent/releases/download/v${GRAFANA_VERSION}/grafana-agent-linux-${ARCH}.zip"
    unzip agent-linux.zip
    cp "grafana-agent-linux-${ARCH}" /usr/local/bin/grafana-agent
    popd

    local PROM_PASSWORD
    local LOKI_PASSWORD
    PROM_PASSWORD=$(get_conf /compiler-explorer/promPassword)
    LOKI_PASSWORD=$(get_conf /compiler-explorer/lokiPassword)
    mkdir -p /etc/grafana
    cp $GRAFANA_CONFIG /etc/grafana/agent.yaml.tpl
    sed -i "s/@PROM_PASSWORD@/${PROM_PASSWORD}/g" /etc/grafana/agent.yaml.tpl
    sed -i "s/@LOKI_PASSWORD@/${LOKI_PASSWORD}/g" /etc/grafana/agent.yaml.tpl
    chmod 600 /etc/grafana/agent.yaml.tpl
    if [ "${INSTALL_TYPE}" = "ci" ]; then
      cp /infra/grafana/make-config-ci.sh /etc/grafana/make-config.sh
    elif [ "${INSTALL_TYPE}" = "admin" ]; then
      cp /infra/grafana/make-config-admin.sh /etc/grafana/make-config.sh
    else
      cp /infra/grafana/make-config.sh /etc/grafana/make-config.sh
    fi

    cp /infra/grafana/update-metrics.sh /etc/grafana/update-metrics.sh
    cp /infra/grafana/ce-metrics.service /lib/systemd/system/ce-metrics.service
    cp /infra/grafana/grafana-agent.service /lib/systemd/system/grafana-agent.service

    systemctl daemon-reload
    systemctl enable ce-metrics
    systemctl enable grafana-agent
}
setup_grafana

# Skip NFS setup if SKIP_NFS_SETUP is set
if [ "${SKIP_NFS_SETUP:-}" != "1" ]; then
  mkdir -p /efs
  if ! grep "/efs nfs" /etc/fstab; then
    echo "fs-db4c8192.efs.us-east-1.amazonaws.com:/ /efs nfs nfsvers=4.1,rsize=1048576,wsize=1048576,hard,timeo=600,retrans=2,noresvport${EXTRA_NFS_ARGS} 0 0" >>/etc/fstab
  fi
fi

# Configure email
SMTP_PASS=$(aws ssm get-parameter --name /admin/smtp_pass | jq -r .Parameter.Value)
cat >/etc/ssmtp/ssmtp.conf <<EOF
root=postmaster
mailhub=email-smtp.us-east-1.amazonaws.com
hostname=compiler-explorer.com
FromLineOverride=NO
AuthUser=AKIAJZWPG4D3SSK45LJA
AuthPass=${SMTP_PASS}
UseTLS=YES
UseSTARTTLS=YES
EOF
cat >/etc/ssmtp/revaliases <<EOF
ubuntu:admin@compiler-explorer.com:email-smtp.us-east-1.amazonaws.com
EOF

if [ "${INSTALL_TYPE}" = "ci" ]; then
  chfn -f 'Compiler Explorer Admin' ubuntu
else
  chfn -f 'Compiler Explorer Build Agent' ubuntu
fi
chmod 640 /etc/ssmtp/*

# Skip mount if NFS was skipped
if [ "${SKIP_NFS_SETUP:-}" != "1" ]; then
  mount -a
fi

cd /home/ubuntu/

mkdir -p /home/ubuntu/.ssh
mkdir -p /tmp/auth_keys
aws s3 sync s3://compiler-explorer/authorized_keys /tmp/auth_keys
cat /tmp/auth_keys/* >>/home/ubuntu/.ssh/authorized_keys
rm -rf /tmp/auth_keys
chown -R ubuntu /home/ubuntu/.ssh

setup_cefs() {
    # We can hit "too many open files" during autofs mount, so increase limits.
    mkdir -p /etc/systemd/system/autofs.service.d
    cat >/etc/systemd/system/autofs.service.d/limits.conf <<EOF
[Service]
LimitNOFILE=65536
EOF
    systemctl daemon-reload
    # This part of the manual setup should be kept in sync with `ce_install cefs setup`
    # To save us having to install `uv` etc in our packer stages we duplicate
    # the setup here.
    mkdir /cefs
    echo "* -fstype=autofs program:/etc/auto.cefs.sub" > /etc/auto.cefs
    cat > /etc/auto.cefs.sub << 'EOF'
#!/bin/bash
key="$1"
subdir="${key:0:2}"
echo "-fstype=squashfs,loop,nosuid,nodev,ro :/efs/cefs-images/${subdir}/${key}.sqfs"
EOF
    chmod +x /etc/auto.cefs.sub
    echo "/cefs /etc/auto.cefs --negative-timeout 1" > /etc/auto.master.d/cefs.autofs
    service autofs restart
}

# Skip CEFS setup if SKIP_CEFS_SETUP is set
if [ "${SKIP_CEFS_SETUP:-}" != "1" ]; then
  setup_cefs
fi
