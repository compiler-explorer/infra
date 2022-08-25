from typing import List

import click

from lib.cli import cli
from lib.instance import AdminInstance
from lib.ssh import run_remote_shell, exec_remote_to_stdout


@cli.group()
def admin():
    """
    Administrative instance commands
    """


@admin.command(name="login")
@click.option("--mosh/--ssh", help="Use mosh to connect")
def admin_login(mosh: bool):
    """Log in to the administrative instance."""
    run_remote_shell(AdminInstance.instance(), use_mosh=mosh)


@admin.command(name="exec")
@click.argument("command", nargs=-1)
def admin_exec(command: List[str]):
    """Execute a command on the admin instance."""
    exec_remote_to_stdout(AdminInstance.instance(), command)


@admin.command(name="info")
def admin_info():
    """Shows address of the admin instance."""
    click.echo(f"Admin instance is at: {AdminInstance.instance().address}")


@admin.command(name="gotty")
def admin_gotty():
    """Runs gotty on the admin instance to allow external viewers to watch the tmux session."""
    instance = AdminInstance.instance()
    port = 5986  # happens to be open in the firewall...
    click.echo(f"Will be PUBLICALLY accessible at: http://{instance.address}:{port}...")
    exec_remote_to_stdout(instance, ["./gotty", "--port", str(port), "tmux", "attach"])
