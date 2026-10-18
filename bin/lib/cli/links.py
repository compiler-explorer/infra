from __future__ import annotations

import datetime
from collections import Counter
from pprint import pformat

import click

from lib.amazon import (
    delete_s3_links,
    delete_short_link,
    expand_short_link,
    get_short_link,
    list_short_links,
    put_short_link,
)
from lib.ce_utils import are_you_sure
from lib.cli import cli
from lib.links_ip_scrub import (
    AddressClassifier,
    apply_updates,
    fetch_ip_ranges,
    format_report,
    point_in_time_recovery,
    scan_links,
)


@cli.group()
def link():
    """Link manipulation commands."""


@link.command()
@click.argument("short_id")
def expand(short_id: str):
    """Expand the full link for a short link."""
    short_link = expand_short_link(short_id)
    print(pformat(short_link))


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
        raise RuntimeError(f"Couldn't find base link {link_from}")
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
    print(f"New link: {pformat(base_link)}")
    if are_you_sure(f"create new link named {link_to}"):
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
        raise RuntimeError(f"Couldn't find base link {link_from}")
    link_to_update = get_short_link(link_to)
    if not link_to_update:
        raise RuntimeError(f"Couldn't find existing short link {link_to}")
    link_to_update["full_hash"] = base_link["full_hash"]
    print(f"New link: {pformat(link_to_update)}")
    if are_you_sure(f"update link named {link_to}"):
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

    if are_you_sure(f"delete {len(dbdirty_set)} db elements:\n{dbdirty_set}\n") and not dry_run:
        for item in dbdirty_set:
            print(f"Deleting {item}")
            delete_short_link(item)
    if are_you_sure(f"delete {len(s3dirty_set)} s3 elements:\n{s3dirty_set}\n") and not dry_run:
        delete_s3_links(s3dirty_set)


@link.command(name="scrub-ips")
@click.option("--apply", "apply", is_flag=True, help="Write the changes; without this nothing is modified")
@click.option("--segments", type=click.IntRange(1, 64), default=16, show_default=True, help="Parallel scan segments")
@click.option(
    "--writes-per-second",
    type=click.FloatRange(min=1, max=200),
    default=25,
    show_default=True,
    help="Write rate when applying",
)
def links_scrub_ips(apply: bool, segments: int, writes_per_second: float):
    """Replace unanonymised addresses in links' creation_ip with the anonymised client address.

    Records written before compiler-explorer#9126 can hold a client's real address in a middle
    X-Forwarded-For entry. Each affected record is rewritten to the single anonymised client address
    that records have held since the fix. Only aggregate shapes and masked patterns are printed.

    Dry run unless --apply is given. Writes are conditional on the value the scan saw, so it is safe
    to re-run, and a second run should find nothing to do.
    """
    classifier = AddressClassifier(fetch_ip_ranges())
    report = scan_links(classifier, segments)
    print("\n".join(format_report(report)))

    to_rewrite = len(report.updates)
    if not report.updates:
        print("\nNothing to rewrite.")
        return
    if not apply:
        print(f"\nDRY RUN: would rewrite {to_rewrite:,} records. Pass --apply to do it.")
        return
    if report.unscrubbable:
        raise click.ClickException("Some records cannot be scrubbed automatically; refusing to write any")

    pitr = point_in_time_recovery()
    if pitr["PointInTimeRecoveryStatus"] != "ENABLED":
        raise click.ClickException("Point-in-time recovery is not enabled on links; refusing to write")
    started = datetime.datetime.now(datetime.UTC).isoformat()
    print(f"\nPITR is enabled; latest restorable time {pitr['LatestRestorableDateTime']}.")
    print(f"To undo, restore links to a time before {started}.")
    are_you_sure(f"rewrite creation_ip on {to_rewrite:,} links records")

    outcomes: Counter[str] = Counter()
    try:
        apply_updates(report.updates, writes_per_second, outcomes)
    finally:
        for outcome, count in outcomes.most_common():
            print(f"  {count:>10,}  {outcome}")
