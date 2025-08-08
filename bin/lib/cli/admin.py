import os
import subprocess
from typing import List

import click

from lib.amazon import ec2_client
from lib.cli import cli
from lib.instance import AdminInstance
from lib.ssh import exec_remote_to_stdout, run_remote_shell


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
    click.echo(f"Will be PUBLICLY accessible at: http://{instance.address}:{port}...")
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


@admin.command(name="mount-efs")
@click.option("--local-path", default="/efs", help="Local mount point (default: /efs)")
@click.option("--use-sudo", is_flag=True, help="Use sudo to mount (required for paths outside home directory)")
def admin_mount_efs(local_path: str, use_sudo: bool):
    """Mount the admin node's /efs directory locally via sshfs."""
    instance = AdminInstance.instance()
    remote_path = "/efs"

    # Check if local mount point exists
    if not os.path.exists(local_path):
        click.echo(f"Error: Mount point {local_path} does not exist", err=True)
        click.echo("Please create it first with:", err=True)
        click.echo(f"  sudo mkdir {local_path}", err=True)
        click.echo(f"  sudo chown $USER:$USER {local_path}", err=True)
        return

    # Check if already mounted
    try:
        result = subprocess.run(["mount"], capture_output=True, text=True)
        if f"{instance.address}:{remote_path}" in result.stdout:
            click.echo(f"Already mounted at {local_path}")
            return
    except Exception:
        pass

    # Check ownership of the mount point
    try:
        stat_info = os.stat(local_path)
        getuid = getattr(os, "getuid", None)
        if getuid and stat_info.st_uid != getuid():
            click.echo(f"Warning: You don't own {local_path}. This may cause mount issues.", err=True)
            click.echo(f"Current owner UID: {stat_info.st_uid}, your UID: {getuid()}", err=True)
    except Exception:
        pass

    # Mount via sshfs (readonly)
    # Build sshfs options
    if use_sudo:
        # When using sudo, tell SSH to use the current user's known_hosts file
        home_dir = os.path.expanduser("~")
        known_hosts = f"{home_dir}/.ssh/known_hosts"
        sshfs_options = (
            f"ro,"
            f"reconnect,ServerAliveInterval=120,ServerAliveCountMax=3,"
            f"StrictHostKeyChecking=accept-new,UserKnownHostsFile={known_hosts},allow_other"
        )
    else:
        sshfs_options = "ro,reconnect,ServerAliveInterval=120,ServerAliveCountMax=3"

    sshfs_cmd = [
        "sshfs",
        f"ubuntu@{instance.address}:{remote_path}",
        local_path,
        "-o",
        sshfs_options,
    ]

    if use_sudo:
        # Preserve SSH agent socket when using sudo
        sudo_cmd = ["sudo"]
        if "SSH_AUTH_SOCK" in os.environ:
            sudo_cmd.extend(["--preserve-env=SSH_AUTH_SOCK"])
        sshfs_cmd = sudo_cmd + sshfs_cmd

    click.echo(f"Mounting {instance.address}:{remote_path} to {local_path}...")
    try:
        result = subprocess.run(sshfs_cmd, capture_output=True, text=True)
        if result.returncode == 0:
            click.echo(f"Successfully mounted EFS at {local_path}")
            if use_sudo:
                click.echo(f"Note: Mounted with sudo. To unmount: sudo umount {local_path}")
        else:
            raise subprocess.CalledProcessError(result.returncode, sshfs_cmd, result.stdout, result.stderr)
    except subprocess.CalledProcessError as e:
        click.echo(f"Failed to mount: {e}", err=True)
        if e.stderr:
            click.echo(f"Error: {e.stderr.strip()}", err=True)
        if not use_sudo and "Permission denied" in (e.stderr or ""):
            click.echo(
                "\nPermission denied. When mounting outside your home directory, you need to use sudo.", err=True
            )
            click.echo("Try again with:", err=True)
            click.echo("\n  bin/ce admin mount-efs --use-sudo", err=True)
    except FileNotFoundError:
        click.echo("sshfs not found. Please install it first:", err=True)
        click.echo("  sudo apt-get install sshfs", err=True)


@admin.command(name="unmount-efs")
@click.option("--local-path", default="/efs", help="Local mount point (default: /efs)")
@click.option("--use-sudo", is_flag=True, help="Use sudo to unmount (if mounted with sudo)")
def admin_unmount_efs(local_path: str, use_sudo: bool):
    """Unmount the locally mounted EFS directory."""
    if not os.path.exists(local_path):
        click.echo(f"Mount point {local_path} does not exist")
        return

    # Check if mounted
    try:
        result = subprocess.run(["mount"], capture_output=True, text=True)
        if local_path not in result.stdout:
            click.echo(f"Not mounted at {local_path}")
            return
    except Exception:
        pass

    # Unmount
    umount_cmd = ["umount", local_path]
    if use_sudo:
        umount_cmd = ["sudo"] + umount_cmd

    try:
        subprocess.run(umount_cmd, check=True)
        click.echo(f"Successfully unmounted {local_path}")
    except subprocess.CalledProcessError:
        if not use_sudo:
            # Try fusermount -u as fallback
            try:
                subprocess.run(["fusermount", "-u", local_path], check=True)
                click.echo(f"Successfully unmounted {local_path}")
            except subprocess.CalledProcessError as e:
                click.echo(f"Failed to unmount: {e}", err=True)
                click.echo("If mounted with sudo, try: bin/ce admin unmount-efs --use-sudo", err=True)
        else:
            click.echo("Failed to unmount with sudo", err=True)
