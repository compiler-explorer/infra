#!/bin/bash

set -ex

ENV=$(curl -sf http://169.254.169.254/latest/user-data || true)
ENV=${ENV:-prod}
HOSTNAME=$(hostname)
sed "s/@HOSTNAME@/${HOSTNAME}/g;s/@ENV@/${ENV}/g" /etc/grafana/agent.yaml.tpl > /etc/grafana/agent.yaml
chmod 600 /etc/grafana/agent.yaml
