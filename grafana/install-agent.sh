#!/bin/bash
# Install grafana-agent + ce-metrics and substitute the templated agent.yaml.
#
# Callers control which mount points node_exporter emits filesystem metrics
# for via FS_IGNORE (a regex of mount points to exclude). The default keeps
# the legacy "/-only" behaviour for hosts that have no real data mount; the
# conan node overrides it because /home/ce/.conan_server is what we want to
# alert on.
#
# Optional env vars:
#   INSTALL_TYPE     ci | admin | <empty>  - picks which make-config.sh to use
#   FS_IGNORE        regex of mount points to drop (default '^/.+$')
#   GRAFANA_VERSION  grafana-agent release tag (default 0.41.1)

set -euxo pipefail

GRAFANA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FS_IGNORE=${FS_IGNORE:-'^/.+$'}
INSTALL_TYPE=${INSTALL_TYPE:-}
GRAFANA_VERSION=${GRAFANA_VERSION:-0.41.1}

ARCH=$(dpkg --print-architecture)

get_conf() {
    aws ssm get-parameter --name "$1" | jq -r .Parameter.Value
}

pushd /tmp
curl -sLo agent-linux.zip "https://github.com/grafana/agent/releases/download/v${GRAFANA_VERSION}/grafana-agent-linux-${ARCH}.zip"
unzip -o agent-linux.zip
cp "grafana-agent-linux-${ARCH}" /usr/local/bin/grafana-agent
rm -f agent-linux.zip "grafana-agent-linux-${ARCH}"
popd

# Escape characters that have meaning in sed replacement strings. Without
# this, a value containing &, \, or the delimiter would mis-substitute
# (and for the secrets, potentially produce a corrupted config).
sed_escape() { printf '%s' "$1" | sed -e 's/[\&]/\\&/g; s/#/\\#/g'; }

mkdir -p /etc/grafana
cp "${GRAFANA_DIR}/agent.yaml" /etc/grafana/agent.yaml.tpl

# Disable xtrace while handling secrets so they don't leak into bake logs.
{ set +x; } 2>/dev/null
PROM_PASSWORD=$(get_conf /compiler-explorer/promPassword)
LOKI_PASSWORD=$(get_conf /compiler-explorer/lokiPassword)
sed -i "s#@PROM_PASSWORD@#$(sed_escape "${PROM_PASSWORD}")#g" /etc/grafana/agent.yaml.tpl
sed -i "s#@LOKI_PASSWORD@#$(sed_escape "${LOKI_PASSWORD}")#g" /etc/grafana/agent.yaml.tpl
unset PROM_PASSWORD LOKI_PASSWORD
set -x

sed -i "s#@FS_IGNORE@#$(sed_escape "${FS_IGNORE}")#g" /etc/grafana/agent.yaml.tpl
chmod 600 /etc/grafana/agent.yaml.tpl

case "${INSTALL_TYPE}" in
    ci)    cp "${GRAFANA_DIR}/make-config-ci.sh"    /etc/grafana/make-config.sh ;;
    admin) cp "${GRAFANA_DIR}/make-config-admin.sh" /etc/grafana/make-config.sh ;;
    *)     cp "${GRAFANA_DIR}/make-config.sh"       /etc/grafana/make-config.sh ;;
esac

cp "${GRAFANA_DIR}/update-metrics.sh" /etc/grafana/update-metrics.sh
cp "${GRAFANA_DIR}/ce-metrics.service" /lib/systemd/system/ce-metrics.service
cp "${GRAFANA_DIR}/grafana-agent.service" /lib/systemd/system/grafana-agent.service

systemctl daemon-reload
systemctl enable ce-metrics
systemctl enable grafana-agent
