#!/bin/bash

aws autoscaling create-launch-configuration --launch-configuration-name $1 --image-id $2 --instance-type t2.medium --associate-public-ip-address --iam-instance-profile XaniaBlog --security-groups sg-99df30fd --key-name mattgodbolt --block-device-mappings '[{ "DeviceName": "/dev/sda1", "Ebs": {"VolumeSize": 24, "VolumeType":"gp2", "DeleteOnTermination": true}}]' --instance-monitoring Enabled=False
