#!/usr/bin/python

import time
from string import Template
from config import S3_ACCESS_KEY, S3_SECRET_KEY

import boto.ec2
import boto.ec2.elb


def get_script(filename='user-data-script.sh'):
    template = open(filename).read()
    return Template(template).substitute(
            S3_ACCESS_KEY=S3_ACCESS_KEY,
            S3_SECRET_KEY=S3_SECRET_KEY)


def launch():
    connection = boto.ec2.connect_to_region('us-east-1')
    print "Launching"
    reservation = connection.run_instances(
            #image_id = 'ami-59a4a230', # basic image
            #image_id = 'ami-ea32d482', # GCC Explorer image May 1st
            image_id = 'ami-864d84ee', # 14.04 server
            instance_type = 't2.micro',
            key_name = 'mattgodbolt',
            security_groups = ['quick-start-1'],
            user_data=get_script()
            )
    print "Adding to LB"
    elb = boto.ec2.elb.connect_to_region('us-east-1')
    balancer = elb.get_all_load_balancers(load_balancer_names=['GccExplorer'])
    balancer[0].register_instances([i.id for i in reservation.instances])
    print "done"

if __name__ == '__main__':
    launch()
