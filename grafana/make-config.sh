#!/bin/bash

set -ex

METADATA_TOKEN=$(curl -s -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 21600")
ENV=$(curl -s -H "X-aws-ec2-metadata-token: $METADATA_TOKEN" http://169.254.169.254/latest/meta-data/tags/instance/Environment)

if [ -z "${ENV}" ]; then
    echo "Environment not set!!"
    exit 1
fi

HOSTNAME=$(hostname)
sed "s/@HOSTNAME@/${HOSTNAME}/g;s/@ENV@/${ENV}/g" /etc/grafana/agent.yaml.tpl > /etc/grafana/agent.yaml
chmod 600 /etc/grafana/agent.yaml
