#!/usr/bin/env python

import boto.ec2
import boto.ec2.autoscale
import boto.ec2.elb
from boto.manage.cmdshell import sshclient_from_instance

import time

def get_gcc_ex_group():
    conn = boto.ec2.autoscale.connect_to_region("us-east-1")
    all_groups = conn.get_all_groups(names=["Gcc Explorer"])
    return all_groups[0]

def ensure_at_least_two():
    print "ensuring at least two instances"
    gcc_explorer_group = get_gcc_ex_group()
    prev_min = gcc_explorer_group.min_size
    print "Found {} instances".format(prev_min)
    if prev_min < 2:
        print "Updating min instances to 2"
        gcc_explorer_group.min_size = 2
	gcc_explorer_group.desired_capacity = 2
	gcc_explorer_group.update()
    return prev_min

def await_at_least_two_healthy():
    print "Waiting for at least two healthy instances"
    elb = boto.ec2.elb.connect_to_region('us-east-1')
    balancer = elb.get_all_load_balancers(load_balancer_names=['GccExplorerApp'])[0]
    while True:
        healthy = [s for s in balancer.get_instance_health() if s.state == u'InService']
        if len(healthy) >= 2:
	    print "Found {} healthy".format(len(healthy))
            break
        print "Only {} healthy...waiting".format(len(healthy))
        time.sleep(5)
    print "Enough healthy instances"

def set_back_to(prev):
    print "Putting back the number of instances to {}".format(prev)
    g = get_gcc_ex_group()
    g.min_size = prev
    g.update()

def update_gcc_explorers():
    prev = ensure_at_least_two()
    await_at_least_two_healthy()
    if prev != 1:
        conn = boto.ec2.connect_to_region('us-east-1')
        reservations = conn.get_all_instances()
        for reservation in reservations:
            for instance in reservation.instances:
                if instance.state != 'running':
                    print "Skipping {} instance {}".format(instance.state, instance.id)
                    continue
                if "App" not in instance.tags or instance.tags["App"] != "GccExplorer":
                    print "Skipping non-gcc explorer instance {}".format(instance.id)
                    continue
                print "Connecting to", instance
                ssh_client = sshclient_from_instance(instance, "ec2-mattgodbolt.pem",
                        user_name='ubuntu')
                print "Connected. Running command"
                status, stdout, stderr = ssh_client.run('sudo -i docker pull -a mattgodbolt/gcc-explorer && sudo service gcc-explorer restart')
                print "Status", status
                print "Stdout", stdout
                print "Stderr", stderr
                print "Done, waiting a minute"
                time.sleep(60)
                await_at_least_two_healthy()
    set_back_to(prev)


if __name__ == '__main__':
    update_gcc_explorers()
