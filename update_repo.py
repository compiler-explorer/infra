#!/usr/bin/env python

from build_compiler import connect_ssh, run_command
from update_instances import get_gcc_nodes, ec2


def update(repo):
    for health in get_gcc_nodes():
        instance = ec2.Instance(id=health['Target']['Id'])
        instance.load()
        ssh = connect_ssh(instance.public_ip_address, 'ubuntu')
        run_command(ssh, 'cd {} && git pull && make dist'.format(repo))
    return True


if __name__ == '__main__':
    update("jsbeeb-beta")
