import time
from typing import Sequence

import click

from lib.instance import BuilderInstance
from lib.ssh import run_remote_shell, exec_remote, exec_remote_to_stdout
from .cli import cli


@cli.group()
def builder():
    """Builder machine manipulation commands."""


@builder.command(name='login')
def builder_login():
    """Log in to the builder machine."""
    instance = BuilderInstance.instance()
    run_remote_shell(instance)


@builder.command(name='exec')
@click.argument('remote_cmd', required=True, nargs=-1)
def builder_exec(remote_cmd: Sequence[str]):
    """Execute REMOTE_CMD on the builder instance."""
    instance = BuilderInstance.instance()
    exec_remote_to_stdout(instance, remote_cmd)


@builder.command(name='start')
def builder_start():
    """Start the builder instance."""
    instance = BuilderInstance.instance()
    if instance.status() == 'stopped':
        print("Starting builder instance...")
        instance.start()
        for _ in range(60):
            if instance.status() == 'running':
                break
            time.sleep(1)
        else:
            raise RuntimeError("Unable to start instance, still in state: {}".format(instance.status()))
    for _ in range(60):
        try:
            r = exec_remote(instance, ["echo", "hello"])
            if r.strip() == "hello":
                break
        except Exception as e:  # pylint: disable=broad-except
            print("Still waiting for SSH: got: {}".format(e))
        time.sleep(1)
    else:
        raise RuntimeError("Unable to get SSH access")
    res = exec_remote(instance,
                      ["bash", "-c", "cd infra && git pull && sudo ./setup-builder-startup.sh"])
    print(res)
    print("Builder started OK")


@builder.command(name='stop')
def builder_stop():
    """Stop the builder instance."""
    BuilderInstance.instance().stop()


@builder.command(name='status')
def builder_status():
    """Get the builder status (running or otherwise)."""
    print("Builder status: {}".format(BuilderInstance.instance().status()))
