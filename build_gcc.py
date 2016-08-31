#!/usr/bin/env python

import boto3
import time
import paramiko
import select
import sys
from argparse import ArgumentParser

parser = ArgumentParser(description='Run an ec2 instance to build GCC')
parser.add_argument('-t', '--instance_type', help='Run on instance type TYPE',
        metavar='TYPE', default='c4.8xlarge')
parser.add_argument('--not-ebs', help='Do not use an EBS optimized instance', action='store_true',
        default=False)
parser.add_argument('version', help='Build GCC version')
parser.add_argument('destination', help='Build destination s3 URL')


def connect_ssh(addr, username='rancher'):
    ssh = paramiko.SSHClient()
    ssh.load_system_host_keys()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    while True:
        print "Connecting to {}...".format(addr)
        try:
            ssh.connect(addr, username=username)
        except Exception, e:
            print "Got exception {}".format(e)
            print "Retrying..."
            time.sleep(10)
            continue
        break
    return ssh


def run_command(ssh, command):
    transport = ssh.get_transport()
    channel = transport.open_session()
    channel.set_combine_stderr(True)
    channel.exec_command(command)
    while True:
        if channel.exit_status_ready():
            status = channel.recv_exit_status()
            print "Command returned exit code {}".format(status)
            return status
        rl, wl, xl = select.select([channel], [], [], 5)
        if rl:
            sys.stdout.write(channel.recv(65536))
    channel.close()

if __name__ == '__main__':
    args = parser.parse_args()
    ec2 = boto3.resource('ec2')
    print "Launching a {} instance...".format(args.instance_type)
    instances = ec2.create_instances(
            ImageId='ami-1071ca07',
            KeyName='mattgodbolt',
            SecurityGroupIds=['sg-cdce6cb7'],
            SubnetId='subnet-690ed81e',
            InstanceType=args.instance_type,
            EbsOptimized=not args.not_ebs,
            BlockDeviceMappings=[
                {
                    'DeviceName':'/dev/sda1', 
                    'Ebs': {'VolumeSize': 32, 'DeleteOnTermination': True}
                }
            ],
            MinCount=1,
            MaxCount=1,
            IamInstanceProfile={'Name':'GccBuilder'})
    if len(instances) != 1:
        raise "Wrong number of instances"
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
            Tags=[{'Key': 'Name', 'Value': "Build GCC {}".format(args.version)}])

    ssh = connect_ssh(addr)

    print "Resizing disc"
    run_command(ssh, """
docker run --privileged -i --rm ubuntu bash << EOF
apt-get update
apt-get install -y cloud-guest-utils parted
growpart /dev/xvda 1
partprobe
resize2fs /dev/xvda1
EOF
""")

    print "Building GCC {} to {}".format(args.version, args.destination)
    res = run_command(ssh, "docker run mattgodbolt/gcc-builder bash build.sh {} {}".format(
        args.version, args.destination))
    
    print "Shutting down instance"
    run_command(ssh, "sudo shutdown -h now")

    time.sleep(10)

    if res == 0:
        print "Terminating instance"
        instance.terminate()
    else:
        print "NOT terminating instance as build failed. Stopping instead"
        instance.stop()

