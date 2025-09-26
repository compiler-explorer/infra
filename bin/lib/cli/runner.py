from __future__ import annotations

import sys
import time
from collections.abc import Sequence
from tempfile import NamedTemporaryFile
from typing import TextIO

import boto3
import click

from lib.discovery import copy_discovery_to_prod, discovery_exists, s3_key_for_discovery
from lib.env import Environment
from lib.instance import RunnerInstance
from lib.ssh import exec_remote, exec_remote_to_stdout, get_remote_file, run_remote_shell

from .cli import cli

EXPECTED_REMOTE_COMPILERS = {"gpu", "winprod"}


@cli.group()
def runner():
    """Runner machine manipulation commands."""


@runner.command(name="login")
def runner_login():
    """Log in to the runner machine."""
    instance = RunnerInstance.instance()
    run_remote_shell(instance)


@runner.command(name="exec")
@click.argument("remote_cmd", required=True, nargs=-1)
def runner_exec(remote_cmd: Sequence[str]):
    """Execute REMOTE_CMD on the builder instance."""
    instance = RunnerInstance.instance()
    exec_remote_to_stdout(instance, remote_cmd)


@runner.command(name="pull")
def runner_pull():
    """Execute git pull on the builder instance."""
    instance = RunnerInstance.instance()
    exec_remote_to_stdout(instance, ["bash", "-c", "cd /infra && sudo git pull"])


@runner.command(name="discovery")
def runner_discovery():
    """Execute compiler discovery on the builder instance."""
    instance = RunnerInstance.instance()
    exec_remote_to_stdout(instance, ["bash", "-c", "cd /infra && sudo /infra/init/do-discovery.sh"])


def _s3_key_for(environment, version):
    """Legacy function - use lib.discovery.s3_key_for_discovery instead."""
    return s3_key_for_discovery(environment, version)


_S3_CONFIG = dict(ACL="public-read", StorageClass="REDUCED_REDUNDANCY")


@runner.command(name="uploaddiscovery")
@click.argument(
    "environment", required=True, type=click.Choice([env.value for env in Environment if env != Environment.RUNNER])
)
@click.argument("version", required=True)
@click.option(
    "--skip-remote-checks",
    default="",
    help="Skip checks for remote compilers type REMOTE (comma separated)",
    metavar="REMOTE",
)
def runner_uploaddiscovery(environment: str, version: str, skip_remote_checks: str):
    """Execute compiler discovery on the builder instance."""
    with NamedTemporaryFile(suffix=".json") as temp_json_file:
        get_remote_file(RunnerInstance.instance(), "/home/ce/discovered-compilers.json", temp_json_file.name)
        temp_json_file.seek(0)

        runner_check_discovery_json_contents(temp_json_file.read().decode("utf-8"), skip_remote_checks)
        temp_json_file.seek(0)

        boto3.client("s3").put_object(
            Bucket="compiler-explorer",
            Key=s3_key_for_discovery(environment, version),
            Body=temp_json_file,
            **_S3_CONFIG,
        )


def runner_discoveryexists(environment: str, version: str):
    """Check if a discovery json file exists."""
    return discovery_exists(environment, version)


def runner_check_discovery_json_contents(contents: str, skip_remote_checks: str):
    # The idiomatic thing to do here is to pass a list[str]; but the GH action that runs this makes that tricky.
    # So rather than a bunch of complex bash gymnastics in `compiler-discovery.yml`, we split here
    skipped = {x.strip() for x in skip_remote_checks.split(",") if x.strip()}
    for required_endpoint in EXPECTED_REMOTE_COMPILERS:
        if f"/{required_endpoint}/api" not in contents:
            if required_endpoint in skipped:
                print(f"Discovery check for {required_endpoint} instance compilers would have failed")
                continue
            raise RuntimeError(f"Discovery does not contain {required_endpoint} instance compilers")
    print("Discovery json looks fine")


@runner.command(name="check_discovery_json")
@click.option(
    "--skip-remote-checks",
    default="",
    help="Skip checks for remote compilers type REMOTE (comma separated)",
    metavar="REMOTE",
)
@click.argument("file", required=True, type=click.File(encoding="utf-8"))
def runner_check_discovery_json(file: TextIO, skip_remote_checks: str):
    """Check if a discovery json file contains all the right ingredients."""
    runner_check_discovery_json_contents(file.read(), skip_remote_checks)


@runner.command(name="safeforprod")
@click.argument("environment", required=True, type=click.Choice([env.value for env in Environment if not env.is_prod]))
@click.argument("version", required=True)
def runner_safeforprod(environment: str, version: str):
    """Mark discovery file as safe to use on production."""
    if not copy_discovery_to_prod(environment, version):
        print(f"❌ Discovery file not found for {environment}/{version}")
        sys.exit(1)


@runner.command(name="start")
def runner_start():
    """Start the runner instance."""
    instance = RunnerInstance.instance()
    if instance.status() == "stopped":
        print("Starting runner instance...")
        instance.start()
        for _ in range(60):
            if instance.status() == "running":
                break
            time.sleep(5)
        else:
            raise RuntimeError(f"Unable to start instance, still in state: {instance.status()}")
    for _ in range(60):
        try:
            r = exec_remote(instance, ["echo", "hello"])
            if r.strip() == "hello":
                break
        except RuntimeError as e:
            print(f"Still waiting for SSH: got: {e}")
        time.sleep(5)
    else:
        raise RuntimeError("Unable to get SSH access")

    for _ in range(60):
        try:
            r = exec_remote(instance, ["journalctl", "-u", "compiler-explorer", "-r", "-n", "5", "-q"])
            if (
                "compiler-explorer.service: Deactivated successfully." in r  # 22.04
                or "compiler-explorer.service: Succeeded." in r  # 20.04
            ):
                break
        except:  # noqa: E722
            print("Waiting for startup to complete")
        time.sleep(5)
    else:
        raise RuntimeError("Unable to get SSH access")

    print("Runner started OK")


@runner.command(name="stop")
def runner_stop():
    """Stop the runner instance."""
    RunnerInstance.instance().stop()


@runner.command(name="status")
def runner_status():
    """Get the runner status (running or otherwise)."""
    print(f"Runner status: {RunnerInstance.instance().status()}")
