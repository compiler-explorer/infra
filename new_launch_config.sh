#!/bin/bash

set -ex

BASE_NAME=CompilerExplorer-$(date +%Y%m%d)-$1

COMMON_ARGS=""
COMMON_ARGS+="--associate-public-ip-address "
COMMON_ARGS+="--iam-instance-profile XaniaBlog "
COMMON_ARGS+="--security-groups sg-99df30fd "
COMMON_ARGS+="--key-name mattgodbolt "
COMMON_ARGS+="--ebs-optimized "
COMMON_ARGS+="--block-device-mappings DeviceName=/dev/sda1,Ebs={VolumeSize=10,VolumeType=gp2,DeleteOnTermination=true} "
COMMON_ARGS+="--instance-monitoring Enabled=False "

aws autoscaling create-launch-configuration --launch-configuration-name ${BASE_NAME}-prod-t2 --image-id $1 \
    --instance-type t2.medium \
    ${COMMON_ARGS}

aws autoscaling create-launch-configuration --launch-configuration-name ${BASE_NAME}-prod-c5 --image-id $1 \
    --instance-type c5.large \
    --spot-price 0.05 \
    ${COMMON_ARGS}

aws autoscaling create-launch-configuration --launch-configuration-name ${BASE_NAME}-beta-c5 --image-id $1 \
    --instance-type c5.large \
    --spot-price 0.05 \
    --user-data "Beta" \
    ${COMMON_ARGS}
