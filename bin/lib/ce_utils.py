import itertools
import json
import logging
import time
from typing import Optional, Union, Set, List

import click

from lib.amazon import get_current_key, release_for, get_releases, get_events_file, save_event_file
from lib.env import Config
from lib.releases import Hash, Release

logger = logging.getLogger(__name__)


def sizeof_fmt(num, suffix='B'):
    for unit in ['', 'Ki', 'Mi', 'Gi', 'Ti', 'Pi', 'Ei', 'Zi']:
        if abs(num) < 1024.0:
            return "%3.1f%s%s" % (num, unit, suffix)
        num /= 1024.0
    return "%.1f%s%s" % (num, 'Yi', suffix)


def describe_current_release(cfg: Config):
    current = get_current_key(cfg)
    if not current:
        return "none"
    r = release_for(get_releases(), current)
    if r:
        return str(r)
    else:
        "non-standard release with s3 key '{}'".format(current)


def wait_for_autoscale_state(instance, state):
    logger.info("Waiting for %s to reach autoscale lifecycle '%s'...", instance, state)
    while True:
        autoscale = instance.describe_autoscale()
        if not autoscale:
            logger.error("Instance is not longer in an ASG: stopping")
            return
        cur_state = autoscale['LifecycleState']
        logger.debug("State is %s", cur_state)
        if cur_state == state:
            logger.info("...done")
            return
        time.sleep(5)


def get_events(cfg: Config) -> dict:
    events = json.loads(get_events_file(cfg))
    if 'ads' not in events:
        events['ads'] = []
    if 'decorations' not in events:
        events['decorations'] = []
    if 'motd' not in events:
        events['motd'] = ''
    return events


def save_events(cfg: Config, events):
    save_event_file(cfg, json.dumps(events))


def are_you_sure(name: str, cfg: Optional[Config] = None) -> bool:
    env_name = cfg.env.value if cfg else 'global'
    while True:
        typed = input(
            f'Confirm operation: "{name}" in env {env_name}\nType the name of the environment to proceed: ')
        if typed == env_name:
            return True


def display_releases(current: Union[str, Hash], filter_branches: Set[str], releases: List[Release]):
    max_branch_len = max(10, max((len(release.branch) for release in releases), default=10))
    release_format = '{: <5} {: <' + str(max_branch_len) + '} {: <10} {: <10} {: <14}'
    click.echo(release_format.format('Live', 'Branch', 'Version', 'Size', 'Hash'))
    for _, grouped_releases in itertools.groupby(releases, lambda r: r.branch):
        for release in grouped_releases:
            if not filter_branches or release.branch in filter_branches:
                click.echo(
                    release_format.format(
                        ' -->' if (release.key == current or release.hash == current) else '',
                        release.branch, str(release.version), sizeof_fmt(release.size), str(release.hash))
                )
