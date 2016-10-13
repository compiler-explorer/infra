#!/usr/bin/env python

import boto3
import time
import paramiko
import select
import datetime
import sys
from argparse import ArgumentParser

parser = ArgumentParser(description='Run an ec2 instance to build GCC or clang')
parser.add_argument('-t', '--instance_type', help='Run on instance type TYPE',
        metavar='TYPE', default='c4.8xlarge')
parser.add_argument('--not-ebs', help='Do not use an EBS optimized instance', action='store_true',
        default=False)
parser.add_argument('compiler', help='Build compiler')
parser.add_argument('version', help='Build version')
parser.add_argument('destination', help='Build destination s3 URL')
parser.add_argument('--spot-price', help='Set hourly spot price')


def log(msg):
    print '{} : {}'.format(datetime.datetime.now(), msg)


def connect_ssh(addr, username='rancher'):
    ssh = paramiko.SSHClient()
    ssh.load_system_host_keys()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    while True:
        log("Connecting to {}...".format(addr))
        try:
            ssh.connect(addr, username=username)
        except Exception, e:
            log("Got exception {}".format(e))
            log("Retrying...")
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
            log("Command returned exit code {}".format(status))
            return status
        rl, wl, xl = select.select([channel], [], [], 5)
        if rl:
            sys.stdout.write(channel.recv(65536))
    channel.close()

if __name__ == '__main__':
    args = parser.parse_args()
    ec2 = boto3.resource('ec2')
    client = boto3.client('ec2')
    if args.spot_price:
        log("Requesting a {} spot instance at ${}...".format(args.instance_type, args.spot_price))
        response = client.request_spot_instances(
                SpotPrice=args.spot_price,
                Type='one-time',
                BlockDurationMinutes=60,
                LaunchSpecification={
                    'ImageId': 'ami-1071ca07',
                    'KeyName': 'mattgodbolt',
                    'SecurityGroupIds': ['sg-cdce6cb7'],
                    'SubnetId': 'subnet-690ed81e',
                    'InstanceType': args.instance_type,
                    'EbsOptimized': not args.not_ebs,
                    'BlockDeviceMappings': [
                        {
                            'DeviceName':'/dev/sda1', 
                            'Ebs': {'VolumeSize': 32, 'DeleteOnTermination': True}
                            }
                        ],
                    'IamInstanceProfile': {'Name':'GccBuilder'}
                    })
        sir = response['SpotInstanceRequests']
        if len(sir) != 1:
            raise "Wrong number of instances"
        si = sir[0]
        waiter = client.get_waiter('spot_instance_request_fulfilled')
        spot_ids=[si['SpotInstanceRequestId']]
        waiter.wait(SpotInstanceRequestIds=spot_ids)
        sir = client.describe_spot_instance_requests(SpotInstanceRequestIds=spot_ids)
        si = sir['SpotInstanceRequests'][0]
        if not 'InstanceId' in si:
            log("No instance spawned, status = {}, canceling".format(si['Status']))
            client.cancel_spot_instance_requests(SpotInstanceRequestIds=spot_ids)
            sys.exit(1)

        log("Got instance {} at a price of {}".format(si['InstanceId'], si['ActualBlockHourlyPrice']))
        instance = ec2.Instance(id=si['InstanceId'])
        instance.load()
    else:
        log("Launching a {} instance...".format(args.instance_type))
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
    log("Waiting for instance {} to become running".format(instance))
    time.sleep(30)
    while True:
        instance.load()
        state = instance.state['Name']
        log("State = {}".format(state))
        if state == "running":
            break
        time.sleep(10)
    addr = instance.public_ip_address
    log("Got address {}".format(addr))

    ec2.create_tags(
            Resources=[instance.id],
            Tags=[{'Key': 'Name', 'Value': "Build GCC {}".format(args.version)}])

    ssh = connect_ssh(addr)

    log("Resizing disc")
    run_command(ssh, """
docker run --privileged -i --rm ubuntu bash << EOF
apt-get update
apt-get install -y cloud-guest-utils parted
growpart /dev/xvda 1
partprobe
resize2fs /dev/xvda1
EOF
""")

    log("Building GCC {} to {}".format(args.version, args.destination))
    res = run_command(ssh, "docker run mattgodbolt/{}-builder bash build.sh {} {}".format(
        args.compiler, args.version, args.destination))
    
    log("Shutting down instance")
    run_command(ssh, "sudo shutdown -h now")

    time.sleep(10)

    if res == 0:
        log("Terminating instance")
        instance.terminate()
    else:
        log("NOT terminating instance as build failed. Stopping instead")
        instance.stop()

