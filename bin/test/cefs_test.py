from pathlib import Path

import pytest

from lib.cefs.root_image import CefsRootImage, METADATA_FILENAME, BadCefsImage


@pytest.fixture
def cefs_mountpoint(tmp_path) -> Path:
    result = tmp_path / "some-cefs-root"
    result.mkdir()
    return result


@pytest.fixture
def image_root(tmp_path) -> Path:
    result = tmp_path / "some_image"
    result.mkdir()
    return result


@pytest.fixture
def dest_root(tmp_path) -> Path:
    result = tmp_path / "dest"
    result.mkdir()
    return result


def test_cefs_root_should_handle_no_initial_path(cefs_mountpoint):
    root = CefsRootImage(cefs_mountpoint=cefs_mountpoint)
    assert not root.catalog
    assert not root.metadata


def test_cefs_root_should_handle_empty_dirs(cefs_mountpoint, image_root: Path):
    root = CefsRootImage(directory=image_root, cefs_mountpoint=cefs_mountpoint)
    assert not root.catalog
    assert not root.metadata


def test_cefs_can_read_existing_images(cefs_mountpoint, image_root: Path, dest_root: Path):
    (image_root / "thing").symlink_to(cefs_mountpoint / "thing")
    (image_root / "some" / "sub").mkdir(parents=True)
    (image_root / "some" / "sub" / "directory").symlink_to(cefs_mountpoint / "thing" / "in" / "subdir")
    root = CefsRootImage(directory=image_root, cefs_mountpoint=cefs_mountpoint)
    assert root.catalog == {
        Path("thing"): cefs_mountpoint / "thing",
        Path("some") / "sub" / "directory": cefs_mountpoint / "thing" / "in" / "subdir",
    }
    assert not root.metadata


def test_cefs_can_read_existing_images_metadata(cefs_mountpoint, image_root: Path, dest_root: Path):
    (image_root / METADATA_FILENAME).write_text("Meta\nData\nFTW\n", encoding="utf-8")
    root = CefsRootImage(directory=image_root, cefs_mountpoint=cefs_mountpoint)
    assert root.metadata == ["Meta", "Data", "FTW"]


def test_cefs_is_upset_by_links_to_non_cefs(cefs_mountpoint, image_root: Path, dest_root: Path):
    (image_root / "thing").symlink_to(dest_root)  # just a valid path not in cefs
    with pytest.raises(BadCefsImage, match="Found a symlink that wasn't a symlink to cefs"):
        CefsRootImage(directory=image_root, cefs_mountpoint=cefs_mountpoint)


def test_cefs_is_upset_by_random_files(cefs_mountpoint, image_root: Path, dest_root: Path):
    (image_root / "thing.txt").write_text("I am a mongoose", encoding="utf-8")
    with pytest.raises(BadCefsImage, match="Found an unexpected file"):
        CefsRootImage(directory=image_root, cefs_mountpoint=cefs_mountpoint)


def test_cefs_can_add_metadata(cefs_mountpoint, image_root: Path):
    root = CefsRootImage(directory=image_root, cefs_mountpoint=cefs_mountpoint)
    root.add_metadata("I am metadata")
    assert root.metadata == ["I am metadata"]


def test_cefs_can_render_metadata(cefs_mountpoint, image_root: Path, dest_root: Path):
    root = CefsRootImage(directory=image_root, cefs_mountpoint=cefs_mountpoint)
    root.add_metadata("Line 1")
    root.add_metadata("Line 2")
    root.add_metadata("Line 3")
    root.render_to(dest_root)
    assert (dest_root / METADATA_FILENAME).read_text(encoding="utf-8") == "Line 1\nLine 2\nLine 3\n"


def test_cefs_can_render_existing_links(cefs_mountpoint, image_root: Path, dest_root: Path):
    (image_root / "thing").symlink_to(cefs_mountpoint / "thing")
    root = CefsRootImage(directory=image_root, cefs_mountpoint=cefs_mountpoint)
    root.render_to(dest_root)
    assert (dest_root / "thing").readlink() == Path(cefs_mountpoint / "thing")


def test_cefs_can_render_new_links(cefs_mountpoint, image_root: Path, dest_root: Path):
    root = CefsRootImage(directory=image_root, cefs_mountpoint=cefs_mountpoint)
    root.link_path(Path("something"), cefs_mountpoint / "something")
    root.render_to(dest_root)
    assert (dest_root / "something").readlink() == Path(cefs_mountpoint / "something")


def test_cefs_can_replace_existing_links(cefs_mountpoint, image_root: Path, dest_root: Path):
    (image_root / "thing").symlink_to(cefs_mountpoint / "thing")
    root = CefsRootImage(directory=image_root, cefs_mountpoint=cefs_mountpoint)
    root.link_path(Path("thing"), cefs_mountpoint / "new")
    root.render_to(dest_root)
    assert (dest_root / "thing").readlink() == Path(cefs_mountpoint / "new")
