"""The autofs program map that turns a CEFS lookup name into a squashfs mount."""

from __future__ import annotations

from itertools import product
from pathlib import Path

# init/auto.cefs.sub is the same script for /efs/cefs-images, installed by setup-common.sh to avoid Python and
# any deployment hassle, and checked at start-up by init/start.sh. autofs_test.py keeps the two identical.
LOOKUP_SCRIPT_TEMPLATE = """#!/bin/bash
# Only answer for well-formed CEFS image names (see generate_cefs_filename in
# bin/lib/cefs_manifest.py) whose image exists.
export LC_ALL=C
key="$1"
valid_key='^[0-9a-f]{24}_[A-Za-z0-9._+-]+$'
[[ "${key}" =~ ${valid_key} ]] || exit 1
image="@IMAGE_DIR@/${key:0:2}/${key}.sqfs"
[[ -f "${image}" ]] || exit 1
echo "-fstype=squashfs,loop,nosuid,nodev,ro :${image}"
"""


def make_lookup_script(image_dir: Path) -> str:
    """Return the program map script that autofs runs for each name looked up under a CEFS sub-directory."""
    return LOOKUP_SCRIPT_TEMPLATE.replace("@IMAGE_DIR@", str(image_dir))


# Image names start with a lowercase hex hash, so these are the only directories that can exist under
# a CEFS mount point. autofs starts a nested mount, with its own daemon thread, for each distinct
# first-level name looked up. Listing the prefixes rather than using a `*` wildcard keeps that to at
# most 256 and makes any other name fail at once.
FIRST_LEVEL_PREFIXES = tuple("".join(pair) for pair in product("0123456789abcdef", repeat=2))


def make_first_level_map(lookup_script: Path) -> str:
    """Return the map that hands each valid first-level directory to a nested autofs mount run by `lookup_script`."""
    return "".join(f"{prefix} -fstype=autofs program:{lookup_script}\n" for prefix in FIRST_LEVEL_PREFIXES)
