from typing import Sequence

import click

from lib.cli import cli
from lib.instance import SMBInstance
from lib.ssh import run_remote_shell, exec_remote_to_stdout


@cli.group()
def smb():
    """SMB instance management commands."""


@smb.command(name="login")
def smb_login():
    """Log in to the smb instance."""
    instance = SMBInstance.instance()
    run_remote_shell(instance)


@smb.command(name="exec")
@click.argument("remote_cmd", required=True, nargs=-1)
def smb_exec(remote_cmd: Sequence[str]):
    """Execute the REMOTE_CMD on the smb instance."""
    instance = SMBInstance.instance()
    exec_remote_to_stdout(instance, remote_cmd)
