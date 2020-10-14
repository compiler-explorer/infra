#!/bin/bash

set -ex

HOSTNAME=$(hostname)
sed "s/{{ HOSTNAME }}/${HOSTNAME}/g" /etc/grafana/agent.yaml.tpl > /etc/grafana/agent.yaml
