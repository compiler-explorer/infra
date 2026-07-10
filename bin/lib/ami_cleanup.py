"""Planning logic for cleaning up old, unreferenced AMIs.

See https://github.com/compiler-explorer/infra/issues/2220: packer rebuilds leave the
previous AMI (and its snapshots) behind forever. Only AMIs explicitly opted in via the
CLEANUP_TAG are ever considered; of those we keep anything still referenced by a launch
template or a non-terminated instance, and anything younger than the minimum age. The
minimum age is therefore also the window in which a superseded AMI remains available to
roll back to; beyond that, rollback means rebuilding from packer.
"""

from __future__ import annotations

import datetime
import re
from dataclasses import dataclass, field
from pathlib import Path

CLEANUP_TAG_KEY = "AmiCleanup"
CLEANUP_TAG_VALUE = "auto"
DEFAULT_MINIMUM_AGE_DAYS = 30

# Instances in any of these states pin their source AMI (a stopped instance may be
# restarted; only termination releases the claim).
_LIVE_INSTANCE_STATES = ["pending", "running", "shutting-down", "stopping", "stopped"]


@dataclass(frozen=True)
class AmiInfo:
    image_id: str
    name: str
    creation_date: datetime.datetime
    tags: dict[str, str]
    snapshot_ids: tuple[str, ...]
    size_gb: int

    @property
    def opted_in(self) -> bool:
        return self.tags.get(CLEANUP_TAG_KEY) == CLEANUP_TAG_VALUE


@dataclass
class CleanupPlan:
    to_delete: list[AmiInfo] = field(default_factory=list)
    kept: dict[str, str] = field(default_factory=dict)  # image_id -> reason


def ami_info_from_image(image: dict) -> AmiInfo:
    snapshot_ids = []
    size_gb = 0
    for mapping in image.get("BlockDeviceMappings", []):
        ebs = mapping.get("Ebs", {})
        if "SnapshotId" in ebs:
            snapshot_ids.append(ebs["SnapshotId"])
            size_gb += ebs.get("VolumeSize", 0)
    return AmiInfo(
        image_id=image["ImageId"],
        name=image.get("Name", image["ImageId"]),
        creation_date=datetime.datetime.fromisoformat(image["CreationDate"]),
        tags={tag["Key"]: tag["Value"] for tag in image.get("Tags", [])},
        snapshot_ids=tuple(snapshot_ids),
        size_gb=size_gb,
    )


def describe_own_images(ec2_client) -> list[dict]:
    paginator = ec2_client.get_paginator("describe_images")
    return [image for page in paginator.paginate(Owners=["self"]) for image in page["Images"]]


def plan_ami_cleanup(
    images: list[AmiInfo],
    referenced_image_ids: set[str],
    now: datetime.datetime,
    minimum_age_days: int = DEFAULT_MINIMUM_AGE_DAYS,
    terraform_mentioned_image_ids: set[str] | None = None,
) -> CleanupPlan:
    plan = CleanupPlan()
    for image in sorted(images, key=lambda image: (image.creation_date, image.image_id)):
        if not image.opted_in:
            continue
        age = now - image.creation_date
        if image.image_id in referenced_image_ids:
            plan.kept[image.image_id] = "referenced by a launch template or live instance"
        elif terraform_mentioned_image_ids and image.image_id in terraform_mentioned_image_ids:
            plan.kept[image.image_id] = "mentioned in terraform source"
        elif age < datetime.timedelta(days=minimum_age_days):
            plan.kept[image.image_id] = f"only {age.days} days old (minimum {minimum_age_days})"
        else:
            plan.to_delete.append(image)
    return plan


def is_backup_snapshot(snapshot: dict) -> bool:
    return any(tag["Key"] == "aws:backup:source-resource" for tag in snapshot.get("Tags", []))


def is_ami_debris_snapshot(snapshot: dict) -> bool:
    """True for snapshots that only exist as a side effect of AMI creation; once no AMI
    references them they are safe to delete. Anything else (e.g. a hand-taken
    pre-migration safety snapshot of a volume) is deliberate and must be left alone."""
    return snapshot.get("Description", "").startswith("Created by CreateImage")


_AMI_ID_RE = re.compile(r"\bami-[0-9a-f]{8,17}\b")


def find_terraform_mentioned_image_ids(repo_root: Path | None = None) -> set[str]:
    """Any AMI id literally written in a *.tf file in this repo is treated as referenced,
    comments included. This closes the gap where terraform/ec2.tf pins an image id for a
    singleton instance: launch-template/instance checks only protect it while the instance
    exists. Grepping can only over-protect (the checks are unioned), and it makes the
    "no stale AMI ids in terraform source, even in comments" rule self-enforcing:
    writing an id down keeps the image alive; deleting the mention releases it."""
    if repo_root is None:
        repo_root = Path(__file__).resolve().parent.parent.parent
    mentioned = set()
    for tf_file in repo_root.rglob("*.tf"):
        if any(part.startswith(".") for part in tf_file.relative_to(repo_root).parts):
            continue  # skip .terraform module/provider caches
        mentioned.update(_AMI_ID_RE.findall(tf_file.read_text(encoding="utf-8")))
    return mentioned


def find_referenced_image_ids(ec2_client) -> set[str]:
    """Image ids we must never delete: those a launch template's $Latest/$Default version
    points at (all our ASGs track $Latest), and those any non-terminated instance was
    launched from. See also find_terraform_mentioned_image_ids."""
    referenced = set()
    paginator = ec2_client.get_paginator("describe_launch_templates")
    for page in paginator.paginate():
        for template in page["LaunchTemplates"]:
            versions = ec2_client.describe_launch_template_versions(
                LaunchTemplateId=template["LaunchTemplateId"], Versions=["$Latest", "$Default"]
            )["LaunchTemplateVersions"]
            for version in versions:
                image_id = version["LaunchTemplateData"].get("ImageId")
                if image_id:
                    referenced.add(image_id)
    paginator = ec2_client.get_paginator("describe_instances")
    for page in paginator.paginate(Filters=[{"Name": "instance-state-name", "Values": _LIVE_INSTANCE_STATES}]):
        for reservation in page["Reservations"]:
            for instance in reservation["Instances"]:
                referenced.add(instance["ImageId"])
    return referenced
