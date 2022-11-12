import datetime
from pprint import pformat

import click

from lib.amazon import get_short_link, put_short_link, list_short_links, delete_short_link, delete_s3_links
from lib.ce_utils import are_you_sure
from lib.cli import cli


@cli.group()
def link():
    """Link manipulation commands."""


@link.command(name="name")
@click.argument("link_from")
@click.argument("link_to")
def links_name(link_from: str, link_to: str):
    """Give link LINK_FROM a new name LINK_TO."""
    if len(link_from) < 6:
        raise RuntimeError("from length must be at least 6")
    if len(link_to) < 6:
        raise RuntimeError("to length must be at least 6")
    base_link = get_short_link(link_from)
    if not base_link:
        raise RuntimeError("Couldn't find base link {}".format(link_from))
    base_link["prefix"]["S"] = link_to[0:6]
    base_link["unique_subhash"]["S"] = link_to
    base_link["stats"]["M"]["clicks"]["N"] = "0"
    base_link["creation_ip"]["S"] = "0.0.0.0"
    # It's us, so we don't care about "anonymizing" the time
    base_link["creation_date"]["S"] = datetime.datetime.utcnow().isoformat()
    title = input("Link title: ")
    author = input("Author(s): ")
    if len(author) == 0:
        # We explicitly ignore author = . in the site code
        author = "."
    project = input("Project: ")
    description = input("Description: ")
    base_link["named_metadata"] = {
        "M": {
            "title": {"S": title},
            "author": {"S": author},
            "project": {"S": project},
            "description": {"S": description},
        }
    }
    print("New link: {}".format(pformat(base_link)))
    if are_you_sure("create new link named {}".format(link_to)):
        put_short_link(base_link)


@link.command(name="update")
@click.argument("link_from")
@click.argument("link_to")
def links_update(link_from: str, link_to: str):
    """Update a link; point LINK_FROM to existing LINK_TO."""
    if len(link_from) < 6:
        raise RuntimeError("from length must be at least 6")
    if len(link_to) < 6:
        raise RuntimeError("to length must be at least 6")
    base_link = get_short_link(link_from)
    if not base_link:
        raise RuntimeError("Couldn't find base link {}".format(link_from))
    link_to_update = get_short_link(link_to)
    if not link_to_update:
        raise RuntimeError("Couldn't find existing short link {}".format(link_to))
    link_to_update["full_hash"] = base_link["full_hash"]
    print("New link: {}".format(pformat(link_to_update)))
    if are_you_sure("update link named {}".format(link_to)):
        put_short_link(link_to_update)


@link.command(name="maintenance")
@click.option("--dry-run/--no-dry-run", help="dry run only")
def links_maintenance(dry_run: bool):
    s3links, dblinks = list_short_links()
    s3keys_set = set()
    dbkeys_set = set()
    dbhashes_set = set()
    s3dirty_set = set()
    dbdirty_set = set()
    for page in s3links:
        for state in page["Contents"]:
            if len(state["Key"][6:]) > 1:
                s3keys_set.add(state["Key"][6:])
    for page in dblinks:
        for item in page["Items"]:
            unique_subhash = item["unique_subhash"]["S"]
            full_hash = item["full_hash"]["S"]
            dbkeys_set.add((unique_subhash, full_hash))
            dbhashes_set.add(full_hash)
    for dbkey in dbkeys_set:
        if dbkey[1] not in s3keys_set:
            dbdirty_set.add(dbkey)
    for s3key in s3keys_set:
        if s3key not in dbhashes_set:
            s3dirty_set.add(s3key)

    if are_you_sure("delete {} db elements:\n{}\n".format(len(dbdirty_set), dbdirty_set)) and not dry_run:
        for item in dbdirty_set:
            print("Deleting {}".format(item))
            delete_short_link(item)
    if are_you_sure("delete {} s3 elements:\n{}\n".format(len(s3dirty_set), s3dirty_set)) and not dry_run:
        delete_s3_links(s3dirty_set)
