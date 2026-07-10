from __future__ import annotations

import datetime

import pytest
from lib.ami_cleanup import (
    ami_info_from_image,
    find_terraform_mentioned_image_ids,
    is_ami_debris_snapshot,
    is_backup_snapshot,
    is_recent_snapshot,
    plan_ami_cleanup,
)

NOW = datetime.datetime(2026, 7, 10, tzinfo=datetime.UTC)


def make_image(
    image_id: str,
    name: str,
    age_days: int,
    opted_in: bool = True,
    snapshot_ids: tuple[str, ...] = (),
    size_gb_per_snapshot: int = 8,
):
    created = NOW - datetime.timedelta(days=age_days)
    return ami_info_from_image({
        "ImageId": image_id,
        "Name": name,
        "CreationDate": created.isoformat(),
        "Tags": [{"Key": "AmiCleanup", "Value": "auto"}] if opted_in else [{"Key": "Site", "Value": "CE"}],
        "BlockDeviceMappings": [
            {"Ebs": {"SnapshotId": snapshot_id, "VolumeSize": size_gb_per_snapshot}} for snapshot_id in snapshot_ids
        ],
    })


def test_ami_info_parses_image_fields():
    image = make_image("ami-1", "compiler-explorer packer 24.04 @ 20250806151308", 100, snapshot_ids=("snap-1",))
    assert image.opted_in
    assert image.snapshot_ids == ("snap-1",)
    assert image.size_gb == 8


def test_ami_info_parses_the_creation_date_format_aws_actually_returns():
    image = ami_info_from_image({"ImageId": "ami-1", "CreationDate": "2025-08-06T15:13:08.000Z"})
    assert image.creation_date == datetime.datetime(2025, 8, 6, 15, 13, 8, tzinfo=datetime.UTC)
    assert NOW - image.creation_date > datetime.timedelta(days=300)  # aware maths must work


def test_untagged_images_are_never_touched():
    images = [make_image("ami-1", "fam @ 1", 400, opted_in=False)]
    plan = plan_ami_cleanup(images, set(), NOW)
    assert not plan.to_delete
    assert not plan.kept  # not even reported: it never opted in


def test_referenced_images_are_kept():
    images = [make_image("ami-1", "fam @ 1", 400), make_image("ami-2", "fam @ 2", 200)]
    plan = plan_ami_cleanup(images, {"ami-1"}, NOW)
    assert plan.kept["ami-1"] == "referenced by a launch template or live instance"
    assert [image.image_id for image in plan.to_delete] == ["ami-2"]


def test_young_images_are_kept():
    images = [make_image("ami-1", "fam @ 1", 10), make_image("ami-2", "fam @ 2", 29)]
    plan = plan_ami_cleanup(images, set(), NOW)
    assert not plan.to_delete
    assert plan.kept["ami-1"] == "only 10 days old (minimum 30)"
    assert plan.kept["ami-2"] == "only 29 days old (minimum 30)"


def test_old_unreferenced_images_are_deleted_even_the_newest():
    images = [make_image("ami-old", "fam @ 1", 400), make_image("ami-new", "fam @ 2", 31)]
    plan = plan_ami_cleanup(images, set(), NOW)
    assert [image.image_id for image in plan.to_delete] == ["ami-old", "ami-new"]
    assert not plan.kept


def test_minimum_age_is_configurable():
    images = [make_image("ami-1", "fam @ 1", 10), make_image("ami-2", "fam @ 2", 5)]
    plan = plan_ami_cleanup(images, set(), NOW, minimum_age_days=7)
    assert [image.image_id for image in plan.to_delete] == ["ami-1"]


def test_deletions_are_oldest_first():
    images = [
        make_image("ami-b", "fam @ 2", 200),
        make_image("ami-a", "fam @ 1", 400),
        make_image("ami-c", "fam @ 3", 100),
    ]
    plan = plan_ami_cleanup(images, set(), NOW)
    assert [image.image_id for image in plan.to_delete] == ["ami-a", "ami-b", "ami-c"]


def test_terraform_mentioned_images_are_kept():
    images = [make_image("ami-00000000000000001", "fam @ 1", 400), make_image("ami-00000000000000002", "fam @ 2", 400)]
    plan = plan_ami_cleanup(images, set(), NOW, terraform_mentioned_image_ids={"ami-00000000000000001"})
    assert plan.kept["ami-00000000000000001"] == "mentioned in terraform source"
    assert [image.image_id for image in plan.to_delete] == ["ami-00000000000000002"]


def test_terraform_scan_finds_ami_ids_even_in_comments(tmp_path):
    (tmp_path / "ec2.tf").write_text(
        'locals { runner_image_id = "ami-00000000000000001" }\n'
        '//  ami = "ami-00000000000000002"  # commented-out resources still protect\n'
    )
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "more.tf").write_text('image_id = "ami-0000000000000000f"')
    (tmp_path / "README.md").write_text("ami-000000000000000aa not a tf file")
    (tmp_path / ".terraform").mkdir()
    (tmp_path / ".terraform" / "cached.tf").write_text('ami = "ami-000000000000000bb"')
    assert find_terraform_mentioned_image_ids(tmp_path) == {
        "ami-00000000000000001",
        "ami-00000000000000002",
        "ami-0000000000000000f",
    }


def test_terraform_scan_fails_closed_when_no_tf_files_found(tmp_path):
    with pytest.raises(RuntimeError, match="no .*tf files found"):
        find_terraform_mentioned_image_ids(tmp_path)


def test_recent_snapshots_are_recognised():
    fresh = {"StartTime": NOW - datetime.timedelta(hours=2)}
    old = {"StartTime": NOW - datetime.timedelta(days=400)}
    assert is_recent_snapshot(fresh, NOW, minimum_age=datetime.timedelta(days=1))
    assert not is_recent_snapshot(old, NOW, minimum_age=datetime.timedelta(days=1))


def test_backup_snapshots_are_recognised():
    assert is_backup_snapshot({"Tags": [{"Key": "aws:backup:source-resource", "Value": "x"}]})
    assert not is_backup_snapshot({"Tags": [{"Key": "Name", "Value": "conan-pre-noble-cutover"}]})
    assert not is_backup_snapshot({})


def test_only_createimage_debris_snapshots_are_deletable():
    assert is_ami_debris_snapshot({"Description": "Created by CreateImage(i-123) for ami-456"})
    assert not is_ami_debris_snapshot({"Description": "Pre-storage-migration snapshot 2026-05-07T01:57:07Z"})
    assert not is_ami_debris_snapshot({"Description": ""})
    assert not is_ami_debris_snapshot({})
