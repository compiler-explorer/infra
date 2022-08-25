import json
from typing import TextIO

import click

from lib.amazon import get_events_file, save_event_file
from lib.ce_utils import are_you_sure
from lib.cli import cli
from lib.env import Config


@cli.group(name="events")
def events_group():
    """Low-level manipulation of ads and events."""


@events_group.command(name="to_raw")
@click.pass_obj
def events_to_raw(cfg: Config):
    """Dumps the events file as raw JSON."""
    print(get_events_file(cfg))


@events_group.command(name="from_raw")
@click.pass_obj
def events_from_raw(cfg: Config):
    """Reloads the events file as raw JSON from console input."""
    raw = input()
    save_event_file(cfg, json.dumps(json.loads(raw)))


@events_group.command(name="to_file")
@click.argument("file", type=click.File(mode="w"))
@click.pass_obj
def events_to_file(cfg: Config, file: TextIO):
    """Saves the raw events file as FILE."""
    file.write(get_events_file(cfg))


@events_group.command(name="from_file")
@click.argument("file", type=click.File(mode="r"))
@click.pass_obj
def events_from_file(cfg: Config, file: TextIO):
    """Reads FILE and replaces the events file with its contents."""
    new_contents = json.loads(file.read())
    if are_you_sure(f"load events from file {file.name}", cfg):
        save_event_file(cfg, new_contents)
