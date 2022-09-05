from pathlib import Path

import pytest

from lib.cefs import CefsImage, METADATA_FILENAME, BadCefsRoot


@pytest.fixture
def cefs_root(tmp_path) -> Path:
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


def test_cefs_root_should_handle_no_initial_path(cefs_root: Path):
    root = CefsImage(cefs_root=cefs_root)
    assert not root.catalog
    assert not root.metadata


def test_cefs_root_should_handle_empty_dirs(cefs_root: Path, image_root: Path):
    root = CefsImage(directory=image_root, cefs_root=cefs_root)
    assert not root.catalog
    assert not root.metadata


def test_cefs_can_read_existing_images(cefs_root: Path, image_root: Path, dest_root: Path):
    (image_root / "thing").symlink_to(cefs_root / "thing")
    (image_root / "some" / "sub").mkdir(parents=True)
    (image_root / "some" / "sub" / "directory").symlink_to(cefs_root / "thing" / "in" / "subdir")
    root = CefsImage(directory=image_root, cefs_root=cefs_root)
    assert root.catalog == {
        Path("thing"): cefs_root / "thing",
        Path("some") / "sub" / "directory": cefs_root / "thing" / "in" / "subdir",
    }
    assert not root.metadata


def test_cefs_can_read_existing_images_metadata(cefs_root: Path, image_root: Path, dest_root: Path):
    (image_root / METADATA_FILENAME).write_text("Meta\nData\nFTW\n", encoding="utf-8")
    root = CefsImage(directory=image_root, cefs_root=cefs_root)
    assert root.metadata == ["Meta", "Data", "FTW"]


def test_cefs_is_upset_by_links_to_non_cefs(cefs_root: Path, image_root: Path, dest_root: Path):
    (image_root / "thing").symlink_to(dest_root)  # just a valid path not in cefs
    with pytest.raises(BadCefsRoot, match="Found a symlink that wasn't a symlink to cefs"):
        CefsImage(directory=image_root, cefs_root=cefs_root)


def test_cefs_is_upset_by_random_files(cefs_root: Path, image_root: Path, dest_root: Path):
    (image_root / "thing.txt").write_text("I am a mongoose", encoding="utf-8")
    with pytest.raises(BadCefsRoot, match="Found an unexpected file"):
        CefsImage(directory=image_root, cefs_root=cefs_root)


def test_cefs_can_add_metadata(cefs_root: Path, image_root: Path):
    root = CefsImage(directory=image_root, cefs_root=cefs_root)
    root.add_metadata("I am metadata")
    assert root.metadata == ["I am metadata"]


def test_cefs_can_render_metadata(cefs_root: Path, image_root: Path, dest_root: Path):
    root = CefsImage(directory=image_root, cefs_root=cefs_root)
    root.add_metadata("Line 1")
    root.add_metadata("Line 2")
    root.add_metadata("Line 3")
    root.render_to(dest_root)
    assert (dest_root / METADATA_FILENAME).read_text(encoding="utf-8") == "Line 1\nLine 2\nLine 3\n"


def test_cefs_can_render_existing_links(cefs_root: Path, image_root: Path, dest_root: Path):
    (image_root / "thing").symlink_to(cefs_root / "thing")
    root = CefsImage(directory=image_root, cefs_root=cefs_root)
    root.render_to(dest_root)
    assert (dest_root / "thing").readlink() == Path(cefs_root / "thing")


def test_cefs_can_render_new_links(cefs_root: Path, image_root: Path, dest_root: Path):
    root = CefsImage(directory=image_root, cefs_root=cefs_root)
    root.link_path(Path("something"), cefs_root / "something")
    root.render_to(dest_root)
    assert (dest_root / "something").readlink() == Path(cefs_root / "something")


def test_cefs_can_replace_existing_links(cefs_root: Path, image_root: Path, dest_root: Path):
    (image_root / "thing").symlink_to(cefs_root / "thing")
    root = CefsImage(directory=image_root, cefs_root=cefs_root)
    root.link_path(Path("thing"), cefs_root / "new")
    root.render_to(dest_root)
    assert (dest_root / "thing").readlink() == Path(cefs_root / "new")
