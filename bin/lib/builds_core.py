"""Core build functions without CLI dependencies."""

import datetime
import os
import subprocess
import tempfile
from typing import Optional

import requests

from lib.amazon import (
    download_release_file,
    download_release_fileobj,
    find_latest_release,
    find_release,
    get_ssm_param,
    has_bouncelock_file,
    log_new_build,
    set_current_key,
)
from lib.cdn import DeploymentJob
from lib.cli.runner import runner_discoveryexists
from lib.env import Config
from lib.releases import Release, Version


def old_deploy_staticfiles(branch: Optional[str], versionfile: str) -> None:
    """Deploy static files using the old method (for releases without static_key)."""
    print("Deploying static files")
    downloadfile = versionfile
    filename = "deploy.tar.xz"
    remotefile = (branch + "/" if branch else "") + downloadfile
    download_release_file(remotefile[1:], filename)
    os.mkdir("deploy")
    subprocess.call(["tar", "-C", "deploy", "-Jxf", filename])
    os.remove(filename)
    subprocess.call(["aws", "s3", "sync", "deploy/out/dist/dist", "s3://compiler-explorer/dist/cdn"])
    subprocess.call(["rm", "-Rf", "deploy"])


def deploy_staticfiles_windows(release: Release) -> bool:
    """Deploy static files to CDN for Windows."""
    print("Deploying static files to cdn (Windows)")
    cc = f"public, max-age={int(datetime.timedelta(days=365).total_seconds())}"

    with tempfile.NamedTemporaryFile(suffix=os.path.basename(release.static_key)) as f:
        download_release_fileobj(release.static_key, f)
        f.flush()
        with DeploymentJob(
            f.name, "ce-cdn.net", version=release.version, cache_control=cc, bucket_path="windows"
        ) as job:
            return job.run()


def deploy_staticfiles(release: Release) -> bool:
    """Deploy static files to CDN."""
    print("Deploying static files to cdn")
    cc = f"public, max-age={int(datetime.timedelta(days=365).total_seconds())}"

    with tempfile.NamedTemporaryFile(suffix=os.path.basename(release.static_key)) as f:
        download_release_fileobj(release.static_key, f)
        f.flush()
        with DeploymentJob(f.name, "ce-cdn.net", version=release.version, cache_control=cc) as job:
            return job.run()


def set_version_for_deployment(cfg: Config, version: str, branch: Optional[str] = None) -> bool:
    """Set version for deployment without interactive prompts.
    
    Returns True if successful, False otherwise.
    """
    if has_bouncelock_file(cfg):
        print(f"{cfg.env.value} is currently bounce locked. Cannot set new version.")
        return False
    
    release: Optional[Release] = None
    to_set: Optional[str] = None
    
    if version == "latest":
        release = find_latest_release(cfg, branch or "")
        if not release:
            print(f"Unable to find latest version" + (f" for branch {branch}" if branch else ""))
            return False
    else:
        try:
            release = find_release(cfg, Version.from_string(version))
        except Exception as e:
            print(f"Invalid version format {version}: {e}")
            return False
            
        if not release:
            print(f"Unable to find version {version}")
            return False
    
    to_set = release.key
    
    # Check compiler discovery
    if ((cfg.env.value != "runner") and not cfg.env.is_windows and 
        not runner_discoveryexists(cfg.env.value, str(release.version))):
        print(f"Warning: Compiler discovery has not run for {cfg.env.value}/{release.version}")
        # In deployment context, we proceed anyway
    
    # Log the new build
    try:
        log_new_build(cfg, to_set)
    except Exception as e:
        print(f"Failed to log new build: {e}")
        return False
    
    # Deploy static files
    if release.static_key:
        try:
            if cfg.env.is_windows:
                if not deploy_staticfiles_windows(release):
                    print("Failed to deploy static files (Windows)")
                    return False
            else:
                if not deploy_staticfiles(release):
                    print("Failed to deploy static files")
                    return False
        except Exception as e:
            print(f"Failed to deploy static files: {e}")
            return False
    else:
        # Use old deploy method if no static_key
        old_deploy_staticfiles(None, to_set)
    
    # Set the current key
    try:
        set_current_key(cfg, to_set)
    except Exception as e:
        print(f"Failed to set current key: {e}")
        return False
    
    # Notify sentry
    notify_sentry_deployment(cfg, release)
    
    return True


def notify_sentry_deployment(cfg: Config, release: Release) -> None:
    """Notify Sentry about a deployment. Failures are logged but don't stop deployment."""
    try:
        print("Marking as a release in sentry...")
        token = get_ssm_param("/compiler-explorer/sentryAuthToken")
        result = requests.post(
            f"https://sentry.io/api/0/organizations/compiler-explorer/releases/{release.version}/deploys/",
            data=dict(environment=cfg.env.value),
            headers=dict(Authorization=f"Bearer {token}"),
            timeout=30,
        )
        if not result.ok:
            print(f"Warning: Failed to notify sentry: {result.status_code}")
            # Don't fail deployment for sentry notification failure
        else:
            print("...done")
    except Exception as e:
        print(f"Warning: Failed to notify sentry: {e}")
        # Don't fail deployment for sentry notification failure