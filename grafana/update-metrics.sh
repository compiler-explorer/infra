#!/bin/bash

set -ex

install_ce_metrics() {
    local arch
    local latest_version

    arch=$(dpkg --print-architecture)
    latest_version=$(curl -s https://api.github.com/repos/compiler-explorer/ce-metrics/releases/latest | jq -r '.tag_name')

    rm -f /usr/local/bin/ce-node-exporter

    if ! curl -sL "https://github.com/compiler-explorer/ce-metrics/releases/download/${latest_version}/ce-node-exporter-linux-${arch}.zip" -o /tmp/ce-metrics.zip; then
        echo "Failed to download ce-metrics version ${latest_version} for architecture ${arch}"
        return
    fi
    unzip -o /tmp/ce-metrics.zip -d /tmp
    rm -f /tmp/ce-metrics.zip
    cp /tmp/ce-node-exporter /usr/local/bin
}

install_ce_metrics
