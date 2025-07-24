import itertools
import json
import logging
import socket
import time
from typing import List, Optional, Set, Union

import click

from lib.amazon import get_current_key, get_events_file, get_releases, release_for, save_event_file
from lib.env import Config
from lib.instance import Instance
from lib.releases import Hash, Release

logger = logging.getLogger(__name__)


def sizeof_fmt(num: Union[int, float], suffix="B") -> str:
    for unit in ["", "Ki", "Mi", "Gi", "Ti", "Pi", "Ei", "Zi"]:
        if abs(num) < 1024.0:
            return "%3.1f%s%s" % (num, unit, suffix)
        num /= 1024.0
    return "%.1f%s%s" % (num, "Yi", suffix)


def is_running_on_admin_node() -> bool:
    """Check if the current script is running on the admin node.

    Returns True if running on the admin node, False otherwise.
    This is used to determine which features require admin node access
    (SSH to instances, HTTP health checks, etc.).
    """
    return socket.gethostname() == "admin-node"


def describe_current_release(cfg: Config) -> str:
    current = get_current_key(cfg)
    if not current:
        return "none"
    r = release_for(get_releases(cfg), current)
    if r:
        return str(r)
    else:
        return "non-standard release with s3 key '{}'".format(current)


def wait_for_autoscale_state(instance: Instance, state: str) -> None:
    logger.info("Waiting for %s to reach autoscale lifecycle '%s'...", instance, state)
    while True:
        autoscale = instance.describe_autoscale()
        if not autoscale:
            logger.error("Instance is not longer in an ASG: stopping")
            return
        cur_state = autoscale["LifecycleState"]
        logger.debug("State is %s", cur_state)
        if cur_state == state:
            logger.info("...done")
            return
        time.sleep(5)


def get_events(cfg: Config) -> dict:
    events = json.loads(get_events_file(cfg))
    if "ads" not in events:
        events["ads"] = []
    if "decorations" not in events:
        events["decorations"] = []
    if "motd" not in events:
        events["motd"] = ""
    if "update" not in events:
        events["update"] = ""
    return events


def save_events(cfg: Config, events) -> None:
    save_event_file(cfg, json.dumps(events))


def update_motd(cfg: Config, motd: str) -> str:
    events = get_events(cfg)
    old_motd = events["motd"]
    events["motd"] = motd
    save_events(cfg, events)
    return old_motd


def set_update_message(cfg: Config, message: str):
    events = get_events(cfg)
    events["update"] = message
    save_events(cfg, events)


def are_you_sure(name: str, cfg: Optional[Config] = None) -> bool:
    env_name = cfg.env.value if cfg else "global"
    while True:
        typed = input(f'Confirm operation: "{name}" in env {env_name}\nType the name of the environment to proceed: ')
        if typed == env_name:
            return True


def display_releases(current: Union[str, Hash], filter_branches: Set[str], releases: List[Release]) -> None:
    max_branch_len = max(10, max((len(release.branch) for release in releases), default=10))
    release_format = "{: <5} {: <" + str(max_branch_len) + "} {: <10} {: <10} {: <14}"
    click.echo(release_format.format("Live", "Branch", "Version", "Size", "Hash"))
    for _, grouped_releases in itertools.groupby(releases, lambda r: r.branch):
        for release in grouped_releases:
            if not filter_branches or release.branch in filter_branches:
                click.echo(
                    release_format.format(
                        " -->" if (release.key == current or release.hash == current) else "",
                        release.branch,
                        str(release.version),
                        sizeof_fmt(release.size),
                        str(release.hash),
                    )
                )


def confirm_branch(branch: str) -> bool:
    while True:
        typed = input('Confirm build branch "{}"\nType the name of the branch: '.format(branch))
        if typed == branch:
            return True


def confirm_action(description: str) -> bool:
    typed = input("{}: [Y/N]\n".format(description))
    return typed.upper() == "Y"


def print_elapsed_time(message: str, start_time: float, **kwargs) -> None:
    """Print a message with elapsed time in minutes and seconds format."""
    elapsed_total_secs = int(time.time() - start_time)
    elapsed_mins = elapsed_total_secs // 60
    elapsed_secs = elapsed_total_secs % 60
    formatted_msg = message.format(**kwargs) if kwargs else message
    print(f"{formatted_msg} after {elapsed_mins}m {elapsed_secs}s")


def print_elapsed_minutes(message: str, start_time: float, **kwargs) -> None:
    """Print a message with elapsed time in minutes only."""
    elapsed_mins = int((time.time() - start_time) / 60)
    formatted_msg = message.format(**kwargs) if kwargs else message
    print(f"[{elapsed_mins}m] {formatted_msg}")
