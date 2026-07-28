from __future__ import annotations

import json
import time
from collections.abc import Sequence
from tempfile import NamedTemporaryFile

import boto3
import click

from lib.discovery import s3_key_for_discovery
from lib.instance import WinRunnerInstance
from lib.ssh import exec_remote, exec_remote_to_stdout, get_remote_file, run_remote_shell

from .cli import cli

_S3_CONFIG = dict(ACL="public-read", StorageClass="REDUCED_REDUNDANCY")

# Absolute paths through Win32-OpenSSH's sftp server are rooted at a leading slash.
DISCOVERY_REMOTE_PATH = "/C:/tmp/discovered-compilers.json"
INFRA_DIR = "C:/tmp/infra"

# init/start.ps1 logs this once it has finished setting a runner up. nssm points the cestartup
# service's stdout here.
STARTUP_LOG = "C:/tmp/log/cestartup-svc.log"
STARTUP_DONE_MARKER = "Runner environment, not starting Compiler Explorer"

# Windows discovers ~240 compilers across c, c++ and hlsl. Well under that means something
# failed to enumerate rather than a compiler or two having been retired.
MIN_EXPECTED_COMPILERS = 100


@cli.group(name="win-runner")
def win_runner():
    """Windows runner machine manipulation commands."""


@win_runner.command(name="login")
def win_runner_login():
    """Log in to the Windows runner machine."""
    run_remote_shell(WinRunnerInstance.instance())


@win_runner.command(name="exec")
@click.argument("remote_cmd", required=True, nargs=-1)
def win_runner_exec(remote_cmd: Sequence[str]):
    """Execute REMOTE_CMD on the Windows runner instance."""
    exec_remote_to_stdout(WinRunnerInstance.instance(), remote_cmd)


@win_runner.command(name="pull")
def win_runner_pull():
    """Execute git pull on the Windows runner instance."""
    exec_remote_to_stdout(WinRunnerInstance.instance(), ["git", "-C", INFRA_DIR, "pull"])


@win_runner.command(name="discovery")
def win_runner_discovery():
    """Execute compiler discovery on the Windows runner instance."""
    exec_remote_to_stdout(WinRunnerInstance.instance(), ["pwsh", "-File", f"{INFRA_DIR}/init/do-discovery.ps1"])


def check_discovery_json_contents(contents: str) -> None:
    """Sanity check a Windows discovery json before it goes anywhere near an environment."""
    try:
        compilers = json.loads(contents)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Discovery json is not valid json: {e}") from e

    if not isinstance(compilers, list):
        raise RuntimeError(f"Discovery json is a {type(compilers).__name__}, expected a list")

    num_compilers = len(compilers)
    if num_compilers < MIN_EXPECTED_COMPILERS:
        raise RuntimeError(
            f"Discovery json has only {num_compilers} compilers, expected at least {MIN_EXPECTED_COMPILERS}"
        )

    missing_exe = [c.get("id", "(no id)") for c in compilers if not c.get("exe")]
    if missing_exe:
        raise RuntimeError(f"Discovery json has compilers with no exe: {missing_exe[:5]}")

    print(f"Discovery json looks fine ({num_compilers} compilers)")


@win_runner.command(name="uploaddiscovery")
@click.argument("environment", required=True, type=click.Choice(["winprod", "winstaging"]))
@click.argument("version", required=True)
def win_runner_uploaddiscovery(environment: str, version: str):
    """Download discovery json from the Windows runner and upload it to S3."""
    with NamedTemporaryFile(suffix=".json") as temp_json_file:
        get_remote_file(WinRunnerInstance.instance(), DISCOVERY_REMOTE_PATH, temp_json_file.name)
        temp_json_file.seek(0)

        check_discovery_json_contents(temp_json_file.read().decode("utf-8"))
        temp_json_file.seek(0)

        boto3.client("s3").put_object(
            Bucket="compiler-explorer",
            Key=s3_key_for_discovery(environment, version),
            Body=temp_json_file,
            **_S3_CONFIG,
        )
    print(f"Uploaded discovery for {environment}/{version}")


@win_runner.command(name="start")
def win_runner_start():
    """Start the Windows runner instance."""
    instance = WinRunnerInstance.instance()
    if instance.status() == "stopped":
        print("Starting Windows runner instance...")
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

    # There is no journalctl here, so wait on the marker init/start.ps1 leaves in the startup
    # service's log instead.
    check_log = ["pwsh", "-Command", f"Select-String -Path {STARTUP_LOG} -SimpleMatch '{STARTUP_DONE_MARKER}'"]
    for _ in range(60):
        try:
            if STARTUP_DONE_MARKER in exec_remote(instance, check_log, ignore_errors=True):
                break
        except RuntimeError as e:
            print(f"Waiting for startup to complete: {e}")
        time.sleep(5)
    else:
        raise RuntimeError("Windows runner did not finish starting up")

    print("Windows runner started OK")


@win_runner.command(name="stop")
def win_runner_stop():
    """Stop the Windows runner instance."""
    WinRunnerInstance.instance().stop()


@win_runner.command(name="status")
def win_runner_status():
    """Get the Windows runner status (running or otherwise)."""
    print(f"Windows runner status: {WinRunnerInstance.instance().status()}")
