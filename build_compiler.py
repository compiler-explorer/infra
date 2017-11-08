#!/usr/bin/env python

import boto3
import time
import paramiko
import select
import datetime
import sys
from argparse import ArgumentParser

IAM_PROFILE = {'Name': 'GccBuilder'}
BLOCK_MAPPINGS = [{'DeviceName': '/dev/sda1', 'Ebs': {'VolumeSize': 32, 'DeleteOnTermination': True}}]
IMAGE_ID = 'ami-dfdff3c8'
SECURITY_GROUPS = ['sg-cdce6cb7']
SUBNET_ID = 'subnet-690ed81e'

parser = ArgumentParser(description='Run an ec2 instance to build GCC or clang')
parser.add_argument('-t', '--instance_type', help='Run on instance type TYPE',
                    metavar='TYPE', default='c4.8xlarge')
parser.add_argument('--not-ebs', help='Do not use an EBS optimized instance', action='store_true',
                    default=False)
parser.add_argument('compiler', help='Build compiler')
parser.add_argument('version', help='Build version')
parser.add_argument('destination', help='Build destination s3 URL')
parser.add_argument('--spot-price', help='Set hourly spot price')
parser.add_argument('--block-duration', default=60, help='duration to reserve, in minutes', type=int)
parser.add_argument('--key-pair', default='mattgodbolt', metavar='KEYNAME', help='use KEYNAME to authorize')
parser.add_argument('--key-file', required=True, metavar='FILE', help='use FILE as the private key file')


def log(msg):
    print '{} : {}'.format(datetime.datetime.now(), msg)


def connect_ssh(addr, keyfile, username='rancher'):
    ssh = paramiko.SSHClient()
    ssh.load_system_host_keys()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    while True:
        log("Connecting to {}...".format(addr))
        try:
            ssh.connect(addr, username=username, key_filename=keyfile)
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
            BlockDurationMinutes=args.block_duration,
            LaunchSpecification={
                'ImageId': IMAGE_ID,
                'KeyName': args.key_name,
                'SecurityGroupIds': SECURITY_GROUPS,
                'SubnetId': SUBNET_ID,
                'InstanceType': args.instance_type,
                'EbsOptimized': not args.not_ebs,
                'BlockDeviceMappings': BLOCK_MAPPINGS,
                'IamInstanceProfile': IAM_PROFILE
            })
        sir = response['SpotInstanceRequests']
        if len(sir) != 1:
            raise "Wrong number of instances"
        si = sir[0]
        waiter = client.get_waiter('spot_instance_request_fulfilled')
        spot_ids = [si['SpotInstanceRequestId']]
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
            ImageId=IMAGE_ID,
            KeyName=args.key_name,
            SecurityGroupIds=SECURITY_GROUPS,
            SubnetId=SUBNET_ID,
            InstanceType=args.instance_type,
            EbsOptimized=not args.not_ebs,
            BlockDeviceMappings=BLOCK_MAPPINGS,
            MinCount=1,
            MaxCount=1,
            IamInstanceProfile=IAM_PROFILE)
        if len(instances) != 1:
            raise "Wrong number of instances"
        instance = instances[0]
    log("Waiting for instance {} to become running (will time out a bunch...)".format(instance))
    time.sleep(45)
    while True:
        instance.load()
        state = instance.state['Name']
        log("State = {}".format(state))
        if state == "running":
            break
        time.sleep(15)
    addr = instance.public_ip_address
    log("Got address {}".format(addr))

    ec2.create_tags(
        Resources=[instance.id],
        Tags=[
            {'Key': 'Name', 'Value': "Build {} {}".format(args.compiler, args.version)},
            {'Key': 'Site', 'Value': 'CompilerExplorer'}
        ])

    ssh = connect_ssh(addr, args.key_file)

    log("Waiting for docker daemon...")
    for i in range(10):
        res = run_command(ssh, "docker version")
        if res == 0:
            log("All ok!")
            break
        time.sleep(10)
    if res == 0:
        log("Building {} {} to {}".format(args.compiler, args.version, args.destination))
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
