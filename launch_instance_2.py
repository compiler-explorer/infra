#!/usr/bin/python

import time
from string import Template
from config import DOCKER_CFG

import boto.ec2
import boto.ec2.elb
from boto.ec2.blockdevicemapping import *


def get_script(filename='user-data-script-2.sh'):
    template = open(filename).read()
    return Template(template).substitute(
            DOCKER_CFG=DOCKER_CFG)


def launch():
    connection = boto.ec2.connect_to_region('us-east-1')
    print "Launching"
    dev_sda1 = BlockDeviceType()
    dev_sda1.size = 16
    bdm = BlockDeviceMapping()
    bdm['/dev/sda1'] = dev_sda1
    reservation = connection.run_instances(
            image_id = 'ami-9eaa1cf6', # 14.04 server
            instance_type = 't2.micro',
            key_name = 'mattgodbolt',
            subnet_id = 'subnet-690ed81e',
            security_group_ids = ['sg-99df30fd'], # gcc explorer
            user_data=get_script(),
            block_device_map=bdm,
            dry_run=False
            )
    print "Not Adding to LB (yet)"
    #elb = boto.ec2.elb.connect_to_region('us-east-1')
    #balancer = elb.get_all_load_balancers(load_balancer_names=['GccExplorer'])
    #balancer[0].register_instances([i.id for i in reservation.instances])
    #print "done"

if __name__ == '__main__':
    launch()
