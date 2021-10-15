import os
import time
from typing import Sequence

import click

from lib.instance import RunnerInstance
from lib.ssh import get_remote_file, run_remote_shell, exec_remote, exec_remote_to_stdout
from .cli import cli


@cli.group()
def runner():
    """Runner machine manipulation commands."""


@runner.command(name='login')
def runner_login():
    """Log in to the runner machine."""
    instance = RunnerInstance.instance()
    run_remote_shell(instance)


@runner.command(name='exec')
@click.argument('remote_cmd', required=True, nargs=-1)
def runner_exec(remote_cmd: Sequence[str]):
    """Execute REMOTE_CMD on the builder instance."""
    instance = RunnerInstance.instance()
    exec_remote_to_stdout(instance, remote_cmd)


@runner.command(name='pull')
def runner_pull():
    """Execute git pull on the builder instance."""
    instance = RunnerInstance.instance()
    exec_remote_to_stdout(instance, ['bash', '-c', 'cd /infra && sudo git pull'])


@runner.command(name='discovery')
def runner_discovery():
    """Execute compiler discovery on the builder instance."""
    instance = RunnerInstance.instance()
    exec_remote_to_stdout(instance, ['bash', '-c', 'cd /infra && sudo /infra/init/do-discovery.sh'])


@runner.command(name='uploaddiscovery')
@click.argument('version')
def runner_uploaddiscovery(version: str):
    """Execute compiler discovery on the builder instance."""
    instance = RunnerInstance.instance()
    localtemppath = f'/tmp/{version}.json'
    get_remote_file(instance, '/home/ce/discovered-compilers.json', localtemppath)
    s3path = f's3://compiler-explorer/dist/discovery/{version}.json'
    os.system(f'aws s3 cp --storage-class REDUCED_REDUNDANCY "{localtemppath}" "{s3path}"')
    os.remove(localtemppath)


@runner.command(name='start')
def runner_start():
    """Start the runner instance."""
    instance = RunnerInstance.instance()
    if instance.status() == 'stopped':
        print("Starting runner instance...")
        instance.start()
        for _ in range(60):
            if instance.status() == 'running':
                break
            time.sleep(5)
        else:
            raise RuntimeError("Unable to start instance, still in state: {}".format(instance.status()))
    for _ in range(60):
        try:
            r = exec_remote(instance, ["echo", "hello"])
            if r.strip() == "hello":
                break
        except Exception as e:  # pylint: disable=broad-except
            print("Still waiting for SSH: got: {}".format(e))
        time.sleep(5)
    else:
        raise RuntimeError("Unable to get SSH access")
    print("Runner started OK")


@runner.command(name='stop')
def runner_stop():
    """Stop the runner instance."""
    RunnerInstance.instance().stop()


@runner.command(name='status')
def runner_status():
    """Get the runner status (running or otherwise)."""
    print("Runner status: {}".format(RunnerInstance.instance().status()))
