import logging
import os
import subprocess

logger = logging.getLogger('ssh')


# TODO maybe use paramiko?

def run_remote_shell(instance):
    logger.debug("Running remote shell on {}".format(instance))
    os.system(
        'ssh -o ConnectTimeout=5 -o UserKnownHostsFile=/dev/null '
        '-o StrictHostKeyChecking=no -o LogLevel=ERROR ubuntu@{}'.format(
            instance.instance.public_ip_address))


def exec_remote(instance, command):
    logger.debug("Running '{}' on {}".format(" ".join(command), instance))
    return subprocess.check_output(
        ['ssh', '-o', 'ConnectTimeout=5', '-o', 'UserKnownHostsFile=/dev/null', '-o', 'StrictHostKeyChecking=no',
         '-o', 'LogLevel=ERROR',
         'ubuntu@' + instance.instance.public_ip_address, '--'] + ["'{}'".format(c) for c in command])


def exec_remote_all(instances, command):
    for instance in instances:
        result = exec_remote(instance, command)
        print '{}: {}'.format(instance, result or "(no output)")
