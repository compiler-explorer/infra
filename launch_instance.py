#!/usr/bin/python

import time
from string import Template
from config import *

import boto.ec2
import boto.ec2.elb
from boto.ec2.blockdevicemapping import *


def get_script(filename='user-data-script.sh'):
    template = open(filename).read()
    return Template(template).substitute(
            PUBLIC_KEY=PUBLIC_KEY,
            PRIVATE_KEY=PRIVATE_KEY,
            DOCKER_CFG=DOCKER_CFG)


def launch():
    connection = boto.ec2.connect_to_region('us-east-1')
    print "Launching"
    dev_sda1 = BlockDeviceType()
    dev_sda1.size = 16
    dev_sda1.delete_on_termination = True
    bdm = BlockDeviceMapping()
    bdm['/dev/sda1'] = dev_sda1
    reservation = connection.run_instances(
            image_id = 'ami-9eaa1cf6', # 14.04 server
            instance_type = 't2.micro',
            key_name = 'mattgodbolt',
            subnet_id = 'subnet-1df1e135', # 1d (where reserved instance is)
            security_group_ids = ['sg-99df30fd'], # gcc explorer
            user_data=get_script(),
            block_device_map=bdm,
            dry_run=False
            )
    print "Instance is {}".format(reservation.instances[0].id)

if __name__ == '__main__':
    launch()
