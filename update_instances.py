#!/usr/bin/env python

import boto3

import time
from build_compiler import connect_ssh, run_command

NODES = 'arn:aws:elasticloadbalancing:us-east-1:052730242331:targetgroup/GccExplorerNodes/84e7c7626fd50397'

AS_NAME = 'Gcc Explorer'

ec2 = boto3.resource('ec2')
as_client = boto3.client('autoscaling')
elb_client = boto3.client('elbv2')


def get_gcc_ex_group():
    result = as_client.describe_auto_scaling_groups(AutoScalingGroupNames=[AS_NAME])
    return result['AutoScalingGroups'][0]


def get_gcc_nodes():
    return elb_client.describe_target_health(TargetGroupArn=NODES)['TargetHealthDescriptions']


def ensure_at_least_two():
    print "ensuring at least two instances"
    gcc_explorer_group = get_gcc_ex_group()
    prev_min = gcc_explorer_group['MinSize']
    print "Found {} instances".format(prev_min)
    if prev_min < 2:
        print "Updating min instances to 2"
        as_client.update_auto_scaling_group(AutoScalingGroupName=AS_NAME, MinSize=2, DesiredCapacity=2)
    return prev_min


def await_at_least_two_healthy():
    print "Waiting for at least two healthy instances"
    while True:
        ag = get_gcc_ex_group()
        healthy = [s for s in ag['Instances'] if s['LifecycleState'] == u'InService']
        if len(healthy) >= 2:
            print "Found {} healthy".format(len(healthy))
            break
        print "Only {} healthy...waiting".format(len(healthy))
        time.sleep(5)
    print "Enough healthy instances, waiting for target groups to become healthy"
    while True:
        healthy = [s for s in get_gcc_nodes() if s['TargetHealth']['State'] == 'healthy']
        if len(healthy) >= 2:
            print "Found {} healthy".format(len(healthy))
            break
        print "Only {} healthy...waiting".format(len(healthy))
        time.sleep(5)


def set_back_to(prev):
    print "Putting back the number of instances to {}".format(prev)
    as_client.update_auto_scaling_group(AutoScalingGroupName=AS_NAME, MinSize=prev)


def update_gcc_explorers():
    prev = ensure_at_least_two()
    await_at_least_two_healthy()
    if prev != 1:
        for health in get_gcc_nodes():
            instance = ec2.Instance(id=health['Target']['Id'])
            instance.load()
            ssh = connect_ssh(instance.public_ip_address, 'ubuntu')
            run_command(ssh, 'sudo -i docker pull -a mattgodbolt/gcc-explorer && sudo service gcc-explorer restart')
            print "Done, waiting a minute"
            time.sleep(60)
            await_at_least_two_healthy()
    set_back_to(prev)


if __name__ == '__main__':
    update_gcc_explorers()
