import subprocess
import sys

import click

from lib.cli import cli
from lib.env import Config


@cli.group()
def workflows():
    """Manage GitHub workflows."""


@workflows.command("run")
@click.argument("repo")
@click.argument("workflow")
@click.option("--field", "-f", multiple=True, help="Field to pass to workflow (format: name=value)")
@click.option("--dry-run", is_flag=True, help="Print the command without executing")
@click.pass_obj
def run_generic(cfg: Config, repo: str, workflow: str, field: tuple, dry_run: bool):
    """Trigger any workflow in any Compiler Explorer repository.

    REPO: Repository name (e.g., 'compiler-explorer' or 'infra')
    WORKFLOW: Workflow file name (e.g., 'deploy-win.yml')

    Example:
        ce workflows run compiler-explorer deploy-win.yml -f buildnumber=gh-12345 -f branch=main
    """
    cmd = ["gh", "workflow", "run", workflow]

    for f in field:
        cmd.extend(["--field", f])

    cmd.extend(["-R", f"github.com/compiler-explorer/{repo}"])

    if dry_run:
        print(" ".join(cmd))
    else:
        print(f"Triggering workflow {workflow} in {repo}")
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            if result.stdout:
                print(result.stdout)
            print("Workflow triggered successfully")
        except subprocess.CalledProcessError as e:
            print(f"Failed to trigger workflow: {e.stderr}", file=sys.stderr)
            sys.exit(1)


@workflows.command("run-discovery")
@click.argument("buildnumber")
@click.option(
    "--environment",
    type=click.Choice(["staging", "beta", "prod"]),
    default="staging",
    help="Environment to run discovery for (default: staging)",
)
@click.option("--branch", default="main", help="Branch to use for discovery (default: main)")
@click.option("--skip-remote-checks", default="", help="Comma separated list of remote checks to skip")
@click.option("--dry-run", is_flag=True, help="Print the command without executing")
@click.pass_obj
def run_discovery(
    cfg: Config,
    buildnumber: str,
    environment: str,
    branch: str,
    skip_remote_checks: str,
    dry_run: bool,
):
    """Trigger the compiler discovery workflow.

    BUILDNUMBER: The build number for discovery (e.g., gh-12345)
    """
    cmd = [
        "gh",
        "workflow",
        "run",
        "compiler-discovery.yml",
        "--field",
        f"environment={environment}",
        "--field",
        f"branch={branch}",
        "--field",
        f"buildnumber={buildnumber}",
    ]

    if skip_remote_checks:
        cmd.extend(["--field", f"skip_remote_checks={skip_remote_checks}"])

    cmd.extend(["-R", "github.com/compiler-explorer/infra"])

    if dry_run:
        print(" ".join(cmd))
    else:
        print(f"Triggering compiler discovery for {environment} environment, branch {branch}, build {buildnumber}")
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            if result.stdout:
                print(result.stdout)
            print("Workflow triggered successfully")
        except subprocess.CalledProcessError as e:
            print(f"Failed to trigger workflow: {e.stderr}", file=sys.stderr)
            sys.exit(1)


@workflows.command("deploy-win")
@click.argument("buildnumber")
@click.option("--branch", default="main", help="Branch to deploy (default: main)")
@click.option("--dry-run", is_flag=True, help="Print the command without executing")
@click.pass_obj
def deploy_win(cfg: Config, buildnumber: str, branch: str, dry_run: bool):
    """Trigger Windows deployment in the main compiler-explorer repository.

    BUILDNUMBER: The build number to deploy (e.g., gh-12345)
    """
    cmd = [
        "gh",
        "workflow",
        "run",
        "deploy-win.yml",
        "--field",
        f"buildnumber={buildnumber}",
        "--field",
        f"branch={branch}",
        "-R",
        "github.com/compiler-explorer/compiler-explorer",
    ]

    if dry_run:
        print(" ".join(cmd))
    else:
        print(f"Triggering Windows deployment for build {buildnumber}, branch {branch}")
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            if result.stdout:
                print(result.stdout)
            print("Workflow triggered successfully")
        except subprocess.CalledProcessError as e:
            print(f"Failed to trigger workflow: {e.stderr}", file=sys.stderr)
            sys.exit(1)


@workflows.command("status")
@click.option(
    "--repo",
    default="infra",
    help="Repository to check (default: infra)",
)
@click.option("--limit", "-l", default=10, help="Maximum number of runs to show (default: 10)")
@click.option("--workflow", "-w", help="Filter by workflow name (e.g., 'compiler-discovery.yml')")
@click.option("--status", "-s", help="Filter by status (e.g., 'in_progress', 'completed')")
@click.option("--branch", "-b", help="Filter by branch")
@click.pass_obj
def status(cfg: Config, repo: str, limit: int, workflow: str, status: str, branch: str):
    """Show recent workflow run status.

    Shows recent workflow runs from the specified repository with their current status.
    """
    cmd = ["gh", "run", "list", "-R", f"github.com/compiler-explorer/{repo}", "--limit", str(limit)]

    if workflow:
        cmd.extend(["--workflow", workflow])
    if status:
        cmd.extend(["--status", status])
    if branch:
        cmd.extend(["--branch", branch])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        if result.stdout.strip():
            print(f"Recent workflow runs in {repo}:")
            print(result.stdout)
        else:
            print(f"No workflow runs found in {repo} matching the criteria")
    except subprocess.CalledProcessError as e:
        print(f"Failed to get workflow status: {e.stderr}", file=sys.stderr)
        sys.exit(1)


@workflows.command("watch")
@click.argument("run_id")
@click.option(
    "--repo",
    default="infra",
    help="Repository containing the run (default: infra)",
)
@click.option("--job", help="View specific job within the run")
@click.option("--web", is_flag=True, help="Open run in browser")
@click.pass_obj
def watch(cfg: Config, run_id: str, repo: str, job: str, web: bool):
    """View details of a specific workflow run.

    RUN_ID: The workflow run ID to view
    """
    cmd = ["gh", "run", "view", run_id, "-R", f"github.com/compiler-explorer/{repo}"]

    if job:
        cmd.extend(["--job", job])
    if web:
        cmd.append("--web")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        if result.stdout:
            print(result.stdout)
    except subprocess.CalledProcessError as e:
        print(f"Failed to view workflow run: {e.stderr}", file=sys.stderr)
        sys.exit(1)


@workflows.command("list")
@click.pass_obj
def list_workflows(cfg: Config):
    """List available GitHub workflows."""
    print("Workflows in compiler-explorer/infra:")
    infra_workflows = [
        ("compiler-discovery.yml", "Compiler discovery workflow"),
        ("win-lib-build.yaml", "Windows library build"),
        ("start_staging.yml", "Start staging environment"),
        ("update-compilers.yml", "Update compilers"),
        ("update-libs.yml", "Update libraries"),
    ]
    for workflow_file, description in infra_workflows:
        print(f"  {workflow_file}: {description}")

    print("\nWorkflows in compiler-explorer/compiler-explorer:")
    ce_workflows = [
        ("deploy-win.yml", "Windows deployment"),
    ]
    for workflow_file, description in ce_workflows:
        print(f"  {workflow_file}: {description}")
