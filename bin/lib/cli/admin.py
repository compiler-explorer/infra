from typing import List

import click

from lib.amazon import ec2_client
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


def _is_backup(snapshot: dict) -> bool:
    if "Tags" not in snapshot:
        return False
    for tag in snapshot["Tags"]:
        if tag["Key"] == "aws:backup:source-resource":
            return True
    return False


@admin.command(name="cleanup")
def admin_cleanup():
    """Runs a bunch of cleanup tasks."""
    snapshots_in_use = set()
    # todo fold in the AMI deregistration
    click.echo("Listing AMIs to find in-use snapshots")
    for image in ec2_client.describe_images(Owners=["self"])["Images"]:
        for mapping in image["BlockDeviceMappings"]:
            if "Ebs" in mapping and "SnapshotId" in mapping["Ebs"]:
                snapshots_in_use.add(mapping["Ebs"]["SnapshotId"])
    click.echo(f"Found {len(snapshots_in_use)} snapshots in use")
    click.echo("Listing snapshots...")
    paginator = ec2_client.get_paginator("describe_snapshots")
    for page in paginator.paginate(OwnerIds=["self"]):
        for snapshot in page["Snapshots"]:
            snapshot_id = snapshot["SnapshotId"]
            if _is_backup(snapshot) or snapshot_id in snapshots_in_use:
                continue
            click.echo(f"Snapshot {snapshot} not in use: removing")
            ec2_client.delete_snapshot(SnapshotId=snapshot_id)
    click.echo("done")
