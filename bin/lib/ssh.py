import functools
import itertools
import logging
import os
import shlex

import paramiko
import requests
from requests.exceptions import ConnectTimeout

logger = logging.getLogger('ssh')


@functools.lru_cache()
def running_on_ec2():
    logger.debug("Checking to see if running on ec2...")
    try:
        result = requests.get(
            'http://169.254.169.254/latest/dynamic/instance-identity/document',
            timeout=2)
        logger.debug("Result %s", result)
        if result.ok and result.json():
            logger.debug("Running on ec2")
            return True
        else:
            logger.debug("Not running on ec2")
    except ConnectTimeout:
        logger.debug("Timeout: not running on ec2")
    except OSError:
        logger.debug("OSError: not running on ec2")
    return False


def can_ssh_to(instance) -> bool:
    if running_on_ec2():
        return True
    return instance.instance.public_ip_address is True


def ssh_address_for(instance):
    if running_on_ec2():
        return instance.instance.private_ip_address
    if instance.instance.public_ip_address:
        return instance.instance.public_ip_address
    raise RuntimeError(f"No public address for {instance.instance}")


def run_remote_shell(instance, use_mosh: bool = False):
    logger.debug("Running remote shell on %s", instance)
    ssh_command = 'ssh -o ConnectTimeout=5 ' \
                  '-o UserKnownHostsFile=/dev/null ' \
                  '-o StrictHostKeyChecking=no -o ' \
                  'LogLevel=ERROR'
    if use_mosh:
        ssh_command = f'mosh --ssh=\'{ssh_command}\''
    os.system(f'{ssh_command} ubuntu@{ssh_address_for(instance)}')


def exec_remote(instance, command):
    command = shlex.join(command)
    logger.debug("Running '%s' on %s", command, instance)
    with ssh_client_for(instance) as client:
        (stdin, stdout, stderr) = client.exec_command(command)
        stdin.close()
        stdout_text = stdout.read().decode('utf-8')
        stderr_text = stderr.read().decode('utf-8')
        status = stdout.channel.recv_exit_status()
        if status == 0:
            return stdout_text
        logger.error("Execution of '%s' failed with status %d", command, status)
        logger.warning("Standard error: %s", stderr_text)
        logger.warning("Standard out: %s", stdout_text)
        raise RuntimeError(f"Remote command execution failed with status {status}")


def exec_remote_to_stdout(instance, command):
    command = shlex.join(command)
    logger.debug("Running '%s' on %s", command, instance)
    with ssh_client_for(instance) as client:
        (stdin, stdout, stderr) = client.exec_command(command, get_pty=True)
        stdout: paramiko.ChannelFile
        stdin.close()
        # This isn't exactly what we want: we iterate all of stdout, then all of stderr...
        for line in itertools.chain(stdout, stderr):
            print(line, end='')
        status = stdout.channel.recv_exit_status()
        if status != 0:
            raise RuntimeError(f"Remote command execution failed with status {status}")


def ssh_client_for(instance) -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(hostname=ssh_address_for(instance), username='ubuntu', timeout=5)
    return client


def exec_remote_all(instances, command):
    for instance in instances:
        result = exec_remote(instance, command)
        print(f'{instance}: {result or "(no output)"}')
