#!/bin/bash

set -ex

ENV=$(cloud-init query userdata)
ENV=${ENV:-prod}
HOSTNAME=$(hostname)
sed "s/@HOSTNAME@/${HOSTNAME}/g;s/@ENV@/${ENV}/g" /etc/grafana/agent.yaml.tpl > /etc/grafana/agent.yaml
chmod 600 /etc/grafana/agent.yaml
