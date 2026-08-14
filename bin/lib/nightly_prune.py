"""Selection logic for pruning dated nightly artifacts from S3.

Nightly builds land in ``s3://compiler-explorer/opt/`` as ``<family>-<YYYYMMDD>.tar.<ext>``
and accumulate forever unless something culls them. What may be culled is decided by the
YAML: every ``type: nightly`` installable knows the exact S3 prefix its artifacts use, so
the set of prunable families is derived from the installables themselves rather than from a
name pattern. Anything in the bucket that no installable claims is reported, never deleted.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime

DEFAULT_KEEP_LAST = 5
# An unclaimed family built this recently is not a relic: something is still uploading builds
# nothing installs, which is the blind spot this command exists to make visible.
ACTIVE_WITHIN_DAYS = 30

# Deliberately strict: only a plausible YYYYMMDD immediately before the ".tar" is treated as a
# build date, so a version that merely looks numeric can never be mistaken for a dated build.
_DATED_ARTIFACT_RE = re.compile(
    r"^(?P<family>.+)-(?P<date>20\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01]))\.tar(?:\.[A-Za-z0-9]+)?$"
)


@dataclass(frozen=True, order=True)
class DatedArtifact:
    """One dated build of one family, as it exists in S3."""

    date: str
    key: str
    family: str
    size: int


@dataclass(frozen=True)
class FamilyPlan:
    """What to do with every dated artifact of a single family."""

    family: str
    claimed_by: tuple[str, ...]
    keep: tuple[DatedArtifact, ...]
    remove: tuple[DatedArtifact, ...]

    @property
    def claimed(self) -> bool:
        return bool(self.claimed_by)

    @property
    def bytes_to_remove(self) -> int:
        return sum(artifact.size for artifact in self.remove)

    @property
    def bytes_kept(self) -> int:
        return sum(artifact.size for artifact in self.keep)

    @property
    def newest_date(self) -> str:
        return max(artifact.date for artifact in self.keep + self.remove)

    def built_since(self, cutoff: date) -> bool:
        return datetime.strptime(self.newest_date, "%Y%m%d").date() >= cutoff


@dataclass(frozen=True)
class PrunePlan:
    """The full picture: families the YAML claims, and families it does not."""

    claimed: tuple[FamilyPlan, ...]
    unclaimed: tuple[FamilyPlan, ...]
    claimed_without_artifacts: tuple[str, ...]

    @property
    def to_remove(self) -> tuple[DatedArtifact, ...]:
        return tuple(artifact for family in self.claimed for artifact in family.remove)

    @property
    def bytes_to_remove(self) -> int:
        return sum(artifact.size for artifact in self.to_remove)


def parse_dated_artifact(key: str, size: int, prefix: str) -> DatedArtifact | None:
    """Parse an S3 key into a dated artifact, or None if it is not one.

    ``prefix`` is the bucket subdirectory (e.g. "opt/"); keys outside it, and keys in a
    subdirectory of it, are not dated artifacts.
    """
    if not key.startswith(prefix):
        return None
    name = key[len(prefix) :]
    if "/" in name:
        return None
    match = _DATED_ARTIFACT_RE.match(name)
    if not match:
        return None
    return DatedArtifact(date=match["date"], key=key, family=match["family"], size=size)


def parse_dated_artifacts(objects: Iterable[tuple[str, int]], prefix: str) -> list[DatedArtifact]:
    """Parse (key, size) pairs, dropping everything that is not a dated artifact."""
    parsed = (parse_dated_artifact(key, size, prefix) for key, size in objects)
    return [artifact for artifact in parsed if artifact is not None]


def _plan_family(
    family: str, artifacts: Sequence[DatedArtifact], claimed_by: Sequence[str], keep_last: int
) -> FamilyPlan:
    """Keep the artifacts of the newest ``keep_last`` build dates; remove the rest.

    Ranking is by the date in the key, not by age in days: a family that stopped building
    years ago keeps its newest builds instead of losing all of them. Unclaimed families keep
    everything - deciding their fate is a human's job.
    """
    ordered = sorted(artifacts)
    if not claimed_by:
        return FamilyPlan(family=family, claimed_by=(), keep=tuple(ordered), remove=())
    dates_to_keep = set(sorted({artifact.date for artifact in ordered})[-keep_last:])
    keep = tuple(artifact for artifact in ordered if artifact.date in dates_to_keep)
    remove = tuple(artifact for artifact in ordered if artifact.date not in dates_to_keep)
    return FamilyPlan(family=family, claimed_by=tuple(claimed_by), keep=keep, remove=remove)


def plan_prune(
    artifacts: Iterable[DatedArtifact], claims: Mapping[str, Sequence[str]], keep_last: int = DEFAULT_KEEP_LAST
) -> PrunePlan:
    """Work out what to keep and what to remove.

    ``claims`` maps an S3 family prefix to the names of the installables that own it.
    """
    if keep_last < 1:
        raise ValueError("keep_last must be at least 1: something must always survive")
    if not claims:
        raise ValueError("No nightly installables claim anything: refusing to plan a prune")

    by_family: dict[str, list[DatedArtifact]] = defaultdict(list)
    for artifact in artifacts:
        by_family[artifact.family].append(artifact)

    claimed: list[FamilyPlan] = []
    unclaimed: list[FamilyPlan] = []
    for family, family_artifacts in sorted(by_family.items()):
        plan = _plan_family(family, family_artifacts, claims.get(family, ()), keep_last)
        (claimed if plan.claimed else unclaimed).append(plan)

    absent = tuple(sorted(family for family in claims if family not in by_family))
    return PrunePlan(claimed=tuple(claimed), unclaimed=tuple(unclaimed), claimed_without_artifacts=absent)
