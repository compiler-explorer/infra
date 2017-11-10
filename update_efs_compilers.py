#!/usr/bin/env python

import boto3
import time
import sys
from argparse import ArgumentParser
from build_compiler import connect_ssh, run_command

IMAGE_ID = 'ami-1071ca07'
SECURITY_GROUPS = ['sg-99df30fd']  # CE's degfault
SUBNET_ID = 'subnet-690ed81e'

parser = ArgumentParser(description='Update the EFS mount')
parser.add_argument('-t', '--instance_type', help='Run on instance type TYPE',
                    metavar='TYPE', default='t2.micro')
parser.add_argument('--key-pair-name', default='mattgodbolt', metavar='KEYNAME', help='use KEYNAME to authorize')
parser.add_argument('--key-file', required=True, metavar='FILE', help='use FILE as the private key file')

if __name__ == '__main__':
    args = parser.parse_args()
    ec2 = boto3.resource('ec2')
    print "Launching a {} instance...".format(args.instance_type)
    instances = ec2.create_instances(
        ImageId=IMAGE_ID,
        KeyName=args.key_pair_name,
        SecurityGroupIds=SECURITY_GROUPS,
        SubnetId=SUBNET_ID,
        InstanceType=args.instance_type,
        MinCount=1,
        MaxCount=1,
        IamInstanceProfile={'Name': 'XaniaBlog'})
    if len(instances) != 1:
        raise Exception("Wrong number of instances")
    instance = instances[0]
    print "Waiting for instance {} to become running".format(instance)
    time.sleep(30)
    while True:
        instance.load()
        state = instance.state['Name']
        print "State = {}".format(state)
        if state == "running":
            break
        time.sleep(10)
    addr = instance.public_ip_address
    print "Got address {}".format(addr)

    ec2.create_tags(
        Resources=[instance.id],
        Tags=[{'Key': 'Name', 'Value': "Update EFS"}])

    ssh = connect_ssh(addr, args.key_file)

    res = run_command(ssh,
                      "docker run --privileged -i mattgodbolt/gcc-builder:update ./efs_update.sh")

    print "Shutting down instance"
    run_command(ssh, "sudo shutdown -h now")

    time.sleep(10)

    print "Terminating instance"
    instance.terminate()

    sys.exit(res)
