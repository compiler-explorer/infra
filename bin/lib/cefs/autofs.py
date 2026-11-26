"""The autofs program map that turns a CEFS lookup name into a squashfs mount."""

from __future__ import annotations

from pathlib import Path

# setup-common.sh writes the same script for /efs/cefs-images avoiding Python and
# any delpoyment hassle. autofs_test.py checks that the two stay identical.
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
