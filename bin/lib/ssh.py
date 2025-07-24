import functools
import logging
import os
import shlex
import subprocess

import paramiko
import requests
from requests.exceptions import ConnectTimeout

logger = logging.getLogger("ssh")


@functools.lru_cache()
def running_on_ec2():
    logger.debug("Checking to see if running on ec2...")
    try:
        result = requests.get("http://169.254.169.254/latest/dynamic/instance-identity/document", timeout=2)
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


def can_ssh_to(_instance) -> bool:
    # We now restrict all ingress to nodes from outside ec2
    return running_on_ec2()


def ssh_address_for(instance):
    if running_on_ec2():
        return instance.instance.private_ip_address
    if instance.instance.public_ip_address:
        return instance.instance.public_ip_address
    raise RuntimeError(f"No public address for {instance.instance}")


_SSH_COMMAND = [
    "ssh",
    "-oConnectTimeout=1",
    "-oUserKnownHostsFile=/dev/null",
    "-oStrictHostKeyChecking=no",
    "-oLogLevel=ERROR",
]


def run_remote_shell(instance, use_mosh: bool = False):
    logger.debug("Running remote shell on %s", instance)
    ssh_command = shlex.join(_SSH_COMMAND)
    if use_mosh:
        ssh_command = f"mosh --ssh='{ssh_command}'"
    os.system(f"{ssh_command} ubuntu@{ssh_address_for(instance)}")


def exec_remote(instance, command, ignore_errors: bool = False):
    command = shlex.join(command)
    logger.debug("Running '%s' on %s", command, instance)
    ssh_command = _SSH_COMMAND + [f"ubuntu@{ssh_address_for(instance)}", command]
    with subprocess.Popen(
        args=ssh_command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8"
    ) as ssh_process:
        stdout_text, stderr_text = ssh_process.communicate()
    status = ssh_process.returncode
    if status != 0 and not ignore_errors:
        logger.error("Execution of '%s' failed with status %d", command, status)
        logger.warning("Standard error: %s", stderr_text)
        logger.warning("Standard out: %s", stdout_text)
        raise RuntimeError(f"Remote command execution failed with status {status}")
    return stdout_text


def exec_remote_to_stdout(instance, command):
    command = shlex.join(command)
    logger.debug("Running '%s' on %s", command, instance)
    ssh_command = _SSH_COMMAND + [f"ubuntu@{ssh_address_for(instance)}", command]
    with subprocess.Popen(args=ssh_command, stdin=subprocess.DEVNULL) as ssh_process:
        ssh_process.wait()
    status = ssh_process.returncode
    if status != 0:
        raise RuntimeError(f"Remote command execution failed with status {status}")


def get_remote_file(instance, remotepath, localpath):
    with ssh_client_for(instance) as client:
        sftpsession = client.open_sftp()
        sftpsession.get(remotepath, localpath)


def ssh_client_for(instance) -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=ssh_address_for(instance), username="ubuntu", timeout=0.2, banner_timeout=0.2, auth_timeout=0.2
    )
    return client


def exec_remote_all(instances, command):
    for instance in instances:
        result = exec_remote(instance, command)
        print(f"{instance}: {result or '(no output)'}")
