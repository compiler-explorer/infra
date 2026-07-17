from __future__ import annotations

from collections.abc import Sequence

import click

from lib.cli import cli
from lib.instance import ConanInstance
from lib.ssh import can_ssh_to, exec_remote, exec_remote_to_stdout, run_remote_shell


@cli.group()
def conan():
    """Conan instance management commands."""


@conan.command(name="status")
def conan_status():
    """Show the status of the conan instance."""
    instance = ConanInstance.instance()
    instance.instance.load()
    state = instance.instance.state["Name"]
    print(f"Instance:  {instance.instance.id} ({instance.instance.instance_type})")
    print(f"State:     {state}")
    if state != "running":
        return
    print(f"Address:   {instance.instance.private_ip_address}")
    if not can_ssh_to(instance):
        print("(cannot SSH to instance from here)")
        return
    service_output = exec_remote(instance, ["systemctl", "is-active", "ce-conan"], ignore_errors=True).strip()
    print(f"Service:   {service_output}")
    disk_output = exec_remote(instance, ["df", "-h", "/", "/home/ce/.conan_server"]).strip()
    print(f"Disk:\n{disk_output}")


@conan.command(name="login")
def conan_login():
    """Log in to the conan instance."""
    instance = ConanInstance.instance()
    run_remote_shell(instance)


@conan.command(name="exec")
@click.argument("remote_cmd", required=True, nargs=-1)
def conan_exec(remote_cmd: Sequence[str]):
    """Execute the REMOTE_CMD on the conan instance."""
    instance = ConanInstance.instance()
    exec_remote_to_stdout(instance, remote_cmd)


@conan.command(name="restart")
def conan_restart():
    """Restart the conan instance."""
    instance = ConanInstance.instance()
    exec_remote(instance, ["sudo", "service", "ce-conan", "restart"])


@conan.command(name="reloadwww")
def conan_reloadwww():
    """Reload the conan web."""
    instance = ConanInstance.instance()
    exec_remote(instance, ["sudo", "git", "-C", "/home/ubuntu/ceconan/conanproxy", "pull"])
