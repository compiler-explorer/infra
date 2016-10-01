#!/usr/bin/env python

import boto3
import time
import sys
from argparse import ArgumentParser
from build_gcc import connect_ssh, run_command

parser = ArgumentParser(description='Update the EFS mount')
parser.add_argument('-t', '--instance_type', help='Run on instance type TYPE',
                    metavar='TYPE', default='t2.micro')

if __name__ == '__main__':
    args = parser.parse_args()
    ec2 = boto3.resource('ec2')
    print "Launching a {} instance...".format(args.instance_type)
    instances = ec2.create_instances(
        ImageId='ami-1071ca07',
        KeyName='mattgodbolt',
        SecurityGroupIds=['sg-99df30fd'],
        SubnetId='subnet-690ed81e',
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

    ssh = connect_ssh(addr)

    res = run_command(ssh,
                      "docker run --privileged -i mattgodbolt/gcc-builder:update ./efs_update.sh")

    print "Shutting down instance"
    run_command(ssh, "sudo shutdown -h now")

    time.sleep(10)

    print "Terminating instance"
    instance.terminate()

    sys.exit(res)
