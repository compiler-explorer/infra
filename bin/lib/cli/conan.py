from typing import Sequence

import click

from lib.cli import cli
from lib.instance import ConanInstance
from lib.ssh import run_remote_shell, exec_remote_to_stdout, exec_remote


@cli.group()
def conan():
    """Conan instance management commands."""


@conan.command(name='login')
def conan_login():
    """Log in to the conan instance."""
    instance = ConanInstance.instance()
    run_remote_shell(instance)


@conan.command(name='exec')
@click.argument('remote_cmd', required=True, nargs=-1)
def conan_exec(remote_cmd: Sequence[str]):
    """Execute the REMOTE_CMD on the conan instance."""
    instance = ConanInstance.instance()
    exec_remote_to_stdout(instance, remote_cmd)


@conan.command(name='restart')
def conan_restart():
    """Restart the conan instance."""
    instance = ConanInstance.instance()
    exec_remote(instance, ["sudo", "service", "ce-conan", "restart"])


@conan.command(name='reloadwww')
def conan_reloadwww():
    """Reload the conan web."""
    instance = ConanInstance.instance()
    exec_remote(instance, ["sudo", "git", "-C", "/home/ubuntu/ceconan/conanproxy", "pull"])
