"""The autofs program map that turns a CEFS lookup name into a squashfs mount."""

from __future__ import annotations

from itertools import product
from pathlib import Path

# The script as installed on nodes by setup-common.sh (and compared at start-up by init/start.sh). Other image
# directories get the same script with the path swapped.
NODE_LOOKUP_SCRIPT = Path(__file__).resolve().parents[3] / "init" / "auto.cefs.sub"
NODE_IMAGE_DIR = Path("/efs/cefs-images")


def make_lookup_script(image_dir: Path) -> str:
    """Return the program map script that autofs runs for each name looked up under a CEFS sub-directory."""
    script = NODE_LOOKUP_SCRIPT.read_text(encoding="utf-8")
    return script.replace(f'image="{NODE_IMAGE_DIR}/', f'image="{image_dir}/')


# Image names start with a lowercase hex hash, so these are the only directories that can exist under
# a CEFS mount point. autofs starts a nested mount, with its own daemon thread, for each distinct
# first-level name looked up. Listing the prefixes rather than using a `*` wildcard keeps that to at
# most 256 and makes any other name fail at once.
FIRST_LEVEL_PREFIXES = tuple("".join(pair) for pair in product("0123456789abcdef", repeat=2))


def make_first_level_map(lookup_script: Path) -> str:
    """Return the map that hands each valid first-level directory to a nested autofs mount run by `lookup_script`."""
    return "".join(f"{prefix} -fstype=autofs program:{lookup_script}\n" for prefix in FIRST_LEVEL_PREFIXES)
