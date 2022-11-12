import json

import click

from lib.amazon import save_event_file
from lib.ce_utils import get_events, are_you_sure, save_events
from lib.cli import cli
from lib.env import Config


@cli.group(name="motd")
def motd_group():
    """Message of the day manipulation functions."""


@motd_group.command(name="show")
@click.pass_obj
def motd_show(cfg: Config):
    """Prints the message of the day."""
    events = get_events(cfg)
    print('Current motd: "{}"'.format(events["motd"]))


@motd_group.command(name="update")
@click.argument("message", type=str)
@click.pass_obj
def motd_update(cfg: Config, message: str):
    """Updates the message of the day to MESSAGE."""
    events = get_events(cfg)
    if are_you_sure("update motd from: {} to: {}".format(events["motd"], message), cfg):
        events["motd"] = message
        save_event_file(cfg, json.dumps(events))


@motd_group.command(name="clear")
@click.pass_obj
def motd_clear(cfg: Config):
    """Clears the message of the day."""
    events = get_events(cfg)
    if are_you_sure("clear current motd: {}".format(events["motd"]), cfg):
        events["motd"] = ""
        save_events(cfg, events)
