#!/usr/bin/env python3
"""Prune old dated nightly artifacts from S3, driven by the installation YAML."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, timedelta

import click
import humanfriendly

from lib.amazon import delete_s3_objects, list_s3_objects
from lib.ce_install import CliContext, cli
from lib.installable.installable import Installable
from lib.nightly_prune import (
    ACTIVE_WITHIN_DAYS,
    DEFAULT_KEEP_LAST,
    FamilyPlan,
    PrunePlan,
    parse_dated_artifacts,
    plan_prune,
)

_LOGGER = logging.getLogger(__name__)


def claims_from_installables(installables: list[Installable]) -> dict[str, list[str]]:
    """Map each S3 family prefix to the names of the installables that own it."""
    claims: dict[str, list[str]] = defaultdict(list)
    for installable in installables:
        prefix = installable.dated_s3_prefix
        if prefix:
            claims[prefix].append(installable.name)
    return claims


def _describe(plan: FamilyPlan) -> str:
    kept_dates = sorted({artifact.date for artifact in plan.keep})
    kept = f"{len(plan.keep)} object(s) over dates {', '.join(kept_dates)}" if kept_dates else "nothing"
    size = humanfriendly.format_size(plan.bytes_to_remove, binary=True)
    return f"{plan.family}: keeping {kept}; removing {len(plan.remove)} object(s), {size}"


def _print_unclaimed(families: list[FamilyPlan]) -> None:
    for family in families:
        size = humanfriendly.format_size(family.bytes_kept, binary=True)
        print(f"    {family.family}: {len(family.keep)} object(s), {size}, newest {family.newest_date}")


def _print_plan(plan: PrunePlan, keep_last: int) -> None:
    print(f"Claimed by the YAML: {len(plan.claimed)} nightly families (keeping the newest {keep_last} build dates)")
    for family in plan.claimed:
        if not family.remove:
            continue
        print(f"  {_describe(family)}")
        print(f"    claimed by: {', '.join(family.claimed_by)}")
        for artifact in family.remove:
            print(f"    REMOVE {artifact.key} ({humanfriendly.format_size(artifact.size, binary=True)})")
        for artifact in family.keep:
            print(f"    KEEP   {artifact.key} ({humanfriendly.format_size(artifact.size, binary=True)})")
    untouched = [family for family in plan.claimed if not family.remove]
    if untouched:
        print(f"  {len(untouched)} claimed families are already within the limit; nothing to remove from them")

    if plan.claimed_without_artifacts:
        print(f"\nClaimed but no dated artifacts in S3: {', '.join(plan.claimed_without_artifacts)}")

    if plan.unclaimed:
        unclaimed_bytes = sum(family.bytes_kept for family in plan.unclaimed)
        total = humanfriendly.format_size(unclaimed_bytes, binary=True)
        print(f"\nUNCLAIMED: {len(plan.unclaimed)} dated families no installable owns, holding {total}.")
        print("These are NOT pruned: they may be stranded relics, or artifacts that only look")
        print("like nightly builds. Either wire them into the YAML or remove them by hand.")
        cutoff = date.today() - timedelta(days=ACTIVE_WITHIN_DAYS)
        active = [family for family in plan.unclaimed if family.built_since(cutoff)]
        dormant = [family for family in plan.unclaimed if not family.built_since(cutoff)]
        if active:
            print(f"  still being built in the last {ACTIVE_WITHIN_DAYS} days, so growing unchecked:")
            _print_unclaimed(active)
        if dormant:
            print("  dormant:")
            _print_unclaimed(dormant)


@cli.command(name="prune-nightlies")
@click.pass_obj
@click.option(
    "--keep",
    "keep_last",
    type=click.IntRange(min=1),
    default=DEFAULT_KEEP_LAST,
    show_default=True,
    help="Number of build dates to keep for each nightly family",
)
@click.option("--delete", "delete", is_flag=True, help="Actually delete; without this nothing is removed")
def prune_nightlies(context: CliContext, keep_last: int, delete: bool):
    """Remove superseded dated nightly builds from S3.

    Which S3 families may be pruned comes from the installation YAML: every `type: nightly`
    installable knows the prefix its dated artifacts use, so novel names are covered the day
    they are added. Families nothing claims are reported and left alone, as they may be
    stranded leftovers, or pinned artifacts that only look like nightly builds.

    Dry run unless --delete is given.
    """
    bucket = context.installation_context.s3_bucket
    prefix = context.installation_context.s3_dir.rstrip("/") + "/"

    # bypass_enable_check picks up nightlies whatever `if:` guards them, so that a family is
    # never treated as unclaimed just because it was filtered out of this invocation.
    claims = claims_from_installables(context.get_installables([], bypass_enable_check=True))
    if not claims:
        raise click.ClickException("No nightly installables found; refusing to prune anything")
    _LOGGER.info("%d nightly families claimed by the YAML", len(claims))

    artifacts = parse_dated_artifacts(list_s3_objects(bucket, prefix), prefix)
    _LOGGER.info("%d dated artifacts under s3://%s/%s", len(artifacts), bucket, prefix)

    plan = plan_prune(artifacts, claims, keep_last)
    _print_plan(plan, keep_last)

    to_remove = plan.to_remove
    total = humanfriendly.format_size(plan.bytes_to_remove, binary=True)
    if not to_remove:
        print("\nNothing to remove.")
        return

    dry_run = context.installation_context.dry_run or not delete
    if dry_run:
        print(f"\nDRY RUN: would remove {len(to_remove)} object(s), {total}. Pass --delete to do it.")
        return

    print(f"\nRemoving {len(to_remove)} object(s), {total}")
    delete_s3_objects(bucket, [artifact.key for artifact in to_remove])
    print("Done.")
