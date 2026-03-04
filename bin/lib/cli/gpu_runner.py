from __future__ import annotations

import time
from collections.abc import Sequence
from tempfile import NamedTemporaryFile

import boto3
import click

from lib.discovery import s3_key_for_discovery
from lib.instance import GpuRunnerInstance
from lib.ssh import exec_remote, exec_remote_to_stdout, get_remote_file, run_remote_shell

from .cli import cli

_S3_CONFIG = dict(ACL="public-read", StorageClass="REDUCED_REDUNDANCY")


@cli.group(name="gpu-runner")
def gpu_runner():
    """GPU runner machine manipulation commands."""


@gpu_runner.command(name="login")
def gpu_runner_login():
    """Log in to the GPU runner machine."""
    run_remote_shell(GpuRunnerInstance.instance())


@gpu_runner.command(name="exec")
@click.argument("remote_cmd", required=True, nargs=-1)
def gpu_runner_exec(remote_cmd: Sequence[str]):
    """Execute REMOTE_CMD on the GPU runner instance."""
    exec_remote_to_stdout(GpuRunnerInstance.instance(), remote_cmd)


@gpu_runner.command(name="pull")
def gpu_runner_pull():
    """Execute git pull on the GPU runner instance."""
    exec_remote_to_stdout(GpuRunnerInstance.instance(), ["bash", "-c", "cd /infra && sudo git pull"])


@gpu_runner.command(name="discovery")
def gpu_runner_discovery():
    """Execute compiler discovery on the GPU runner instance."""
    exec_remote_to_stdout(GpuRunnerInstance.instance(), ["bash", "-c", "cd /infra && sudo /infra/init/do-discovery.sh"])


@gpu_runner.command(name="uploaddiscovery")
@click.argument("environment", required=True, type=click.Choice(["gpu"]))
@click.argument("version", required=True)
def gpu_runner_uploaddiscovery(environment: str, version: str):
    """Download discovery JSON from GPU runner and upload to S3."""
    with NamedTemporaryFile(suffix=".json") as temp_json_file:
        get_remote_file(GpuRunnerInstance.instance(), "/home/ce/discovered-compilers.json", temp_json_file.name)
        temp_json_file.seek(0)

        boto3.client("s3").put_object(
            Bucket="compiler-explorer",
            Key=s3_key_for_discovery(environment, version),
            Body=temp_json_file,
            **_S3_CONFIG,
        )


@gpu_runner.command(name="start")
def gpu_runner_start():
    """Start the GPU runner instance."""
    instance = GpuRunnerInstance.instance()
    if instance.status() == "stopped":
        print("Starting GPU runner instance...")
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
        raise RuntimeError("compiler-explorer service did not exit cleanly")

    print("GPU runner started OK")


@gpu_runner.command(name="stop")
def gpu_runner_stop():
    """Stop the GPU runner instance."""
    GpuRunnerInstance.instance().stop()


@gpu_runner.command(name="status")
def gpu_runner_status():
    """Get the GPU runner status (running or otherwise)."""
    print(f"GPU runner status: {GpuRunnerInstance.instance().status()}")
