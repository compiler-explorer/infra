#!/bin/bash

aws ec2 run-instances \
    --image-id ami-1071ca07 \
    --key-name mattgodbolt \
    --security-group-ids sg-cdce6cb7 \
    --subnet-id subnet-690ed81e \
    --instance-type c4.8xlarge \
    --block-device-mappings 'DeviceName=/dev/sda1,Ebs={VolumeSize=32,DeleteOnTermination=true}' \
    --ebs-optimized \
    --iam-instance-profile 'Name=GccBuilder' \
    --user-data file://gcc_build.yaml \
    --count 1

