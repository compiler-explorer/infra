from __future__ import annotations

import datetime
import os
import subprocess
import sys
from collections.abc import Callable

import click
from botocore.exceptions import ClientError

from lib import ami_cleanup
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
def admin_exec(command: list[str]):
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


_GONE_ERROR_CODES = {"InvalidAMIID.Unavailable", "InvalidAMIID.NotFound", "InvalidSnapshot.NotFound"}


def delete_ignoring_failures(what: str, delete: Callable[..., object], in_use_ok: bool = False, **kwargs: str) -> int:
    """Runs a deletion, tolerating already-gone errors; returns the number of failures (0 or 1).

    A persistent per-item failure must not abort the whole run (the cron would then wedge
    at the same point every day), so failures are reported to stderr and counted instead.
    in_use_ok treats InvalidSnapshot.InUse as benign: right after a deregister_image the
    snapshot delete can transiently see the AMI as still registered; the next run's orphan
    sweep mops it up, so it shouldn't fail the run (and mail) in the meantime."""
    try:
        delete(**kwargs)
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code in _GONE_ERROR_CODES:
            return 0
        if in_use_ok and code == "InvalidSnapshot.InUse":
            click.echo(f"Skipping {what}: still in use; a later orphan sweep will retry")
            return 0
        click.echo(f"Failed to remove {what}: {e}", err=True)
        return 1
    return 0


@admin.command(name="cleanup")
@click.option(
    "--dry-run/--no-dry-run",
    default=True,
    show_default=True,
    help="print what would be deleted without deleting anything",
)
@click.option(
    "--min-age-days",
    default=ami_cleanup.DEFAULT_MINIMUM_AGE_DAYS,
    show_default=True,
    help="never delete AMIs younger than this",
)
def admin_cleanup(dry_run: bool, min_age_days: int):
    """Runs a bunch of cleanup tasks: old opted-in AMIs, then orphaned snapshots.

    Only AMIs tagged AmiCleanup=auto are considered for deregistration; see
    https://github.com/compiler-explorer/infra/issues/2220 for the policy.
    """
    would = "Would remove" if dry_run else "Removing"
    failures = 0

    click.echo("Finding image ids referenced by launch templates and instances...")
    referenced = ami_cleanup.find_referenced_image_ids(ec2_client)
    click.echo(f"Found {len(referenced)} referenced image ids")
    tf_mentioned = ami_cleanup.find_terraform_mentioned_image_ids()
    click.echo(f"Found {len(tf_mentioned)} image ids mentioned in terraform source")
    images = [ami_cleanup.ami_info_from_image(image) for image in ami_cleanup.describe_own_images(ec2_client)]
    plan = ami_cleanup.plan_ami_cleanup(
        images,
        referenced,
        now=datetime.datetime.now(datetime.UTC),
        minimum_age_days=min_age_days,
        terraform_mentioned_image_ids=tf_mentioned,
    )
    for image_id, reason in sorted(plan.kept.items()):
        click.echo(f"Keeping {image_id}: {reason}")
    total_gb = 0
    for image in plan.to_delete:
        click.echo(
            f"{would} {image.image_id} ({image.name}, {image.creation_date:%Y-%m-%d}, {image.size_gb} GB, "
            f"snapshots: {', '.join(image.snapshot_ids) or 'none'})"
        )
        total_gb += image.size_gb
        if not dry_run:
            if delete_ignoring_failures(image.image_id, ec2_client.deregister_image, ImageId=image.image_id):
                failures += 1
                continue  # a registered AMI's snapshots can't be deleted; don't compound the failure
            for snapshot_id in image.snapshot_ids:
                failures += delete_ignoring_failures(
                    snapshot_id, ec2_client.delete_snapshot, in_use_ok=True, SnapshotId=snapshot_id
                )
    not_opted_in = len(images) - len(plan.to_delete) - len(plan.kept)
    click.echo(
        f"AMI summary: {len(plan.to_delete)} removed ({total_gb} GB of snapshots), "
        f"{len(plan.kept)} kept, {not_opted_in} not opted in (no {ami_cleanup.CLEANUP_TAG_KEY} tag)"
        f"{' [dry run: nothing deleted]' if dry_run else ''}"
    )

    snapshots_in_use = set()
    click.echo("Listing AMIs to find in-use snapshots")
    for raw_image in ami_cleanup.describe_own_images(ec2_client):
        for mapping in raw_image["BlockDeviceMappings"]:
            if "Ebs" in mapping and "SnapshotId" in mapping["Ebs"]:
                snapshots_in_use.add(mapping["Ebs"]["SnapshotId"])
    click.echo(f"Found {len(snapshots_in_use)} snapshots in use")
    click.echo("Listing snapshots...")
    paginator = ec2_client.get_paginator("describe_snapshots")
    for page in paginator.paginate(OwnerIds=["self"]):
        for snapshot in page["Snapshots"]:
            snapshot_id = snapshot["SnapshotId"]
            if ami_cleanup.is_backup_snapshot(snapshot) or snapshot_id in snapshots_in_use:
                continue
            if ami_cleanup.is_recent_snapshot(
                snapshot, datetime.datetime.now(datetime.UTC), minimum_age=datetime.timedelta(days=1)
            ):
                continue  # may belong to an in-flight CreateImage (packer can run at any time)
            if not ami_cleanup.is_ami_debris_snapshot(snapshot):
                click.echo(f"Keeping unreferenced snapshot {snapshot_id}: not AMI debris, assumed deliberate")
                continue
            click.echo(f"{would} orphaned snapshot {snapshot_id}")
            if not dry_run:
                failures += delete_ignoring_failures(snapshot_id, ec2_client.delete_snapshot, SnapshotId=snapshot_id)
    if failures:
        click.echo(f"{failures} deletions failed", err=True)
        sys.exit(1)
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
    except RuntimeError:
        pass

    # Check ownership of the mount point
    try:
        stat_info = os.stat(local_path)
        getuid = getattr(os, "getuid", None)
        if getuid and stat_info.st_uid != getuid():
            click.echo(f"Warning: You don't own {local_path}. This may cause mount issues.", err=True)
            click.echo(f"Current owner UID: {stat_info.st_uid}, your UID: {getuid()}", err=True)
    except RuntimeError:
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
    except RuntimeError:
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
