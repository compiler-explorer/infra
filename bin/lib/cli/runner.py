import os
import time
from tempfile import NamedTemporaryFile
from typing import Sequence

import click
import boto3
import botocore.exceptions
from lib.env import EnvironmentNoProd, EnvironmentNoRunner

from lib.instance import RunnerInstance
from lib.ssh import get_remote_file, run_remote_shell, exec_remote, exec_remote_to_stdout
from .cli import cli


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
    if environment == "prod":
        key = f"dist/discovery/release/{version}.json"
    else:
        key = f"dist/discovery/{environment}/{version}.json"
    return key


@runner.command(name="uploaddiscovery")
@click.argument("environment", required=True, type=click.Choice([env.value for env in EnvironmentNoRunner]))
@click.argument("version", required=True)
def runner_uploaddiscovery(environment: str, version: str):
    """Execute compiler discovery on the builder instance."""
    with NamedTemporaryFile(suffix=".json") as temp_json_file:
        get_remote_file(RunnerInstance.instance(), "/home/ce/discovered-compilers.json", temp_json_file.name)
        temp_json_file.seek(0)
        boto3.client("s3").put_object(
            Bucket="compiler-explorer", Key=_s3_key_for(environment, version), Body=temp_json_file
        )


def runner_discoveryexists(environment: str, version: str):
    """Check if a discovery json file exists."""
    try:
        boto3.client("s3").head_object(Bucket="compiler-explorer", Key=_s3_key_for(environment, version))
    except botocore.exceptions.ClientError as e:
        if e.response["Error"]["Code"] == "404":
            return False
        raise
    return True


@runner.command(name="safeforprod")
@click.argument("environment", required=True, type=click.Choice([env.value for env in EnvironmentNoProd]))
@click.argument("version", required=True)
def runner_safeforprod(environment: str, version: str):
    """Mark discovery file as safe to use on production."""
    boto3.client("s3").copy_object(
        Bucket="compiler-explorer",
        CopySource=dict(Bucket="compiler-explorer", Key=_s3_key_for(environment, version)),
        Key=_s3_key_for("prod", version),
    )


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

    for _ in range(60):
        try:
            r = exec_remote(instance, ["journalctl", "-u", "compiler-explorer", "-r", "-n", "1", "-q"])
            if "compiler-explorer.service: Succeeded." in r:
                break
        except:  # pylint: disable=bare-except
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
    print("Runner status: {}".format(RunnerInstance.instance().status()))
