#!/bin/bash

set -ex

sed "s/@HOSTNAME@/admin-node/g;s/@ENV@/admin/g" /etc/grafana/agent.yaml.tpl > /etc/grafana/agent.yaml
chmod 600 /etc/grafana/agent.yaml
