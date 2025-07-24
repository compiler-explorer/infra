#!/bin/bash

set -ex

ENV=CI
HOSTNAME=$(hostname)
sed "s/@HOSTNAME@/${HOSTNAME}/g;s/@ENV@/${ENV}/g" /etc/grafana/agent.yaml.tpl > /etc/grafana/agent.yaml
chmod 600 /etc/grafana/agent.yaml
