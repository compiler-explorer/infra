import json
import re
from typing import Sequence

import click

from lib.amazon import save_event_file
from lib.ce_utils import get_events, are_you_sure
from lib.cli import cli
from lib.env import Config

DECORATION_FORMAT = "{: <10} {: <15} {: <30} {: <50}"


@cli.group()
def decorations():
    """Manage the decorations (ok, Easter Eggs)."""


@decorations.command(name="list")
@click.pass_obj
def decorations_list(cfg: Config):
    events = get_events(cfg)
    print(DECORATION_FORMAT.format("Name", "Filters", "Regex", "Decoration"))
    for dec in events["decorations"]:
        print(DECORATION_FORMAT.format(dec["name"], str(dec["filter"]), dec["regex"], json.dumps(dec["decoration"])))


def check_dec_args(regex, decoration):
    try:
        re.compile(regex)
    except re.error as re_err:
        raise RuntimeError(f"Unable to validate regex '{regex}' : {re_err}") from re_err
    try:
        decoration = json.loads(decoration)
    except json.decoder.JSONDecodeError as json_err:
        raise RuntimeError(f"Unable to parse decoration '{decoration}' : {json_err}") from json_err
    return regex, decoration


@decorations.command(name="add")
@click.pass_obj
@click.option("--filter", "lang_filter", help="filter for this language", multiple=True)
@click.argument("name")
@click.argument("regex")
@click.argument("decoration")
def decorations_add(cfg: Config, lang_filter: Sequence[str], name: str, regex: str, decoration: str):
    """
    Add a decoration called NAME matching REGEX resulting in json DECORATION.
    """
    events = get_events(cfg)
    if name in [d["name"] for d in events["decorations"]]:
        raise RuntimeError(f"Duplicate decoration name {name}")
    regex, decoration = check_dec_args(regex, decoration)

    new_decoration = {"name": name, "filter": lang_filter, "regex": regex, "decoration": decoration}
    if are_you_sure(
        "add decoration: {}".format(
            DECORATION_FORMAT.format(
                new_decoration["name"],
                str(new_decoration["filter"]),
                new_decoration["regex"],
                json.dumps(new_decoration["decoration"]),
            )
        ),
        cfg,
    ):
        events["decorations"].append(new_decoration)
        save_event_file(cfg, json.dumps(events))


@decorations.command(name="remove")
@click.pass_obj
@click.option("--force/--no-force", help="force without confirmation")
@click.argument("name")
def decorations_remove(cfg: Config, name: str, force: bool):
    """Remove a decoration."""
    events = get_events(cfg)
    for i, dec in enumerate(events["decorations"]):
        if dec["name"] == name:
            if force or are_you_sure(
                "remove decoration: {}".format(
                    DECORATION_FORMAT.format(
                        dec["name"], str(dec["filter"]), dec["regex"], json.dumps(dec["decoration"])
                    )
                ),
                cfg,
            ):
                del events["decorations"][i]
                save_event_file(cfg, json.dumps(events))
            break


@decorations.command(name="clear")
@click.pass_obj
def decorations_clear(cfg: Config):
    """Clear all decorations."""
    events = get_events(cfg)
    if are_you_sure("clear all decorations (count: {})".format(len(events["decorations"])), cfg):
        events["decorations"] = []
        save_event_file(cfg, json.dumps(events))


@decorations.command(name="edit")
@click.pass_obj
@click.option("--filter", "lang_filter", help="filter for this language", multiple=True)
@click.option("--regex", help="match REGEX")
@click.option("--decoration", help="evaluate to DECORATION (json syntax)")
@click.argument("name")
def decorations_edit(cfg: Config, lang_filter: Sequence[str], name: str, regex: str, decoration: str):
    """Edit existing decoration NAME."""
    events = get_events(cfg)

    for i, dec in enumerate(events["decorations"]):
        if dec["name"] == name:
            regex, decoration = check_dec_args(regex or dec["regex"], decoration or json.dumps(dec["decoration"]))
            new_dec = {
                "name": dec["name"],
                "filter": lang_filter or dec["filter"],
                "regex": regex,
                "decoration": decoration,
            }
            print(
                "{}\n{}\n{}".format(
                    DECORATION_FORMAT.format("Name", "Filters", "Regex", "Decoration"),
                    DECORATION_FORMAT.format("<FROM", str(dec["filter"]), dec["regex"], json.dumps(dec["decoration"])),
                    DECORATION_FORMAT.format(
                        ">TO", str(new_dec["filter"]), new_dec["regex"], json.dumps(new_dec["decoration"])
                    ),
                )
            )
            if are_you_sure("edit decoration: {}".format(dec["name"]), cfg):
                events["decoration"][i] = new_dec
                save_event_file(cfg, json.dumps(events))
            break
