"""Detect whether PR additions require building compilers or tools.

This module analyzes YAML file changes to determine if additions require
CE to build artifacts before they can be deployed.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from lib.config_safe_loader import ConfigSafeLoader

# Installer types that require CE to build/upload to S3
BUILD_REQUIRED_TYPES = frozenset({
    "s3tarballs",
    "non-free-s3tarballs",
    "nightly",
    "nightlytarballs",
    "edg",
})


def get_misc_builder_scripts() -> dict[str, str]:
    """Fetch build scripts from misc-builder repo via GitHub API.

    Returns dict mapping compiler name to build script filename.
    E.g., {"erlang": "build-erlang.sh", "cc65": "buildcc65.sh"}
    """
    try:
        result = subprocess.run(
            ["gh", "api", "repos/compiler-explorer/misc-builder/contents/misc", "--jq", ".[].name"],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return {}

    scripts = {}
    for line in result.stdout.strip().split("\n"):
        if not line.endswith(".sh"):
            continue
        # Extract compiler name from script: build-erlang.sh -> erlang, buildcc65.sh -> cc65
        match = re.match(r"build-?(.+)\.sh", line, re.IGNORECASE)
        if match:
            compiler_name = match.group(1).lower()
            scripts[compiler_name] = line

    return scripts


def get_available_builder_images(workflow_path: Path) -> set[str]:
    """Extract available builder images from the bespoke-build workflow."""
    if not workflow_path.exists():
        return set()

    with open(workflow_path, encoding="utf-8") as f:
        workflow = yaml.safe_load(f)

    try:
        # YAML parses "on" as True, so we need to handle both cases
        on_key = "on" if "on" in workflow else True
        options = workflow[on_key]["workflow_dispatch"]["inputs"]["image"]["options"]
        return set(options)
    except (KeyError, TypeError):
        return set()


@dataclass
class BuildParams:
    """Parameters for triggering a bespoke build."""

    image: str
    version: str
    command: str = "build.sh"


@dataclass
class Addition:
    """Represents a compiler/tool addition that requires building."""

    yaml_file: str
    context: list[str]
    target: str
    installer_type: str

    @property
    def name(self) -> str:
        """Human-readable name for the addition."""
        ctx = "/".join(self.context) if self.context else "root"
        return f"{ctx} {self.target}"

    def get_build_params(
        self, available_images: set[str], misc_scripts: dict[str, str] | None = None
    ) -> BuildParams | None:
        """Try to determine build parameters from context.

        Returns BuildParams if we can map to a known builder image, None otherwise.
        """
        if misc_scripts is None:
            misc_scripts = {}

        # Try to find a matching image from the context
        # Check each part of the context path for a matching image,
        # trying compound names with adjacent parts first (e.g., gcc-cross)
        for i in range(len(self.context) - 1, -1, -1):
            ctx_lower = self.context[i].lower()
            # Context parts after the match position become version prefixes
            # (e.g., "arm" in cross/gcc/arm -> version="arm 11.5.0")
            suffix_parts = [p.lower() for p in self.context[i + 1 :]]
            version = " ".join(suffix_parts + [self.target]) if suffix_parts else self.target

            # Try compound names with the parent context part (more specific match)
            if i > 0:
                parent_lower = self.context[i - 1].lower()
                for compound in (f"{ctx_lower}-{parent_lower}", f"{parent_lower}-{ctx_lower}"):
                    if compound in misc_scripts:
                        return BuildParams(image="misc", version=version, command=misc_scripts[compound])
                    if compound in available_images:
                        return BuildParams(image=compound, version=version)

            # Check if it's a misc builder script
            if ctx_lower in misc_scripts:
                return BuildParams(image="misc", version=version, command=misc_scripts[ctx_lower])

            if ctx_lower in available_images:
                return BuildParams(image=ctx_lower, version=version)

            # Handle hyphenated variants (e.g., rust_linux -> rust-linux)
            ctx_hyphen = ctx_lower.replace("_", "-")
            if ctx_hyphen in misc_scripts:
                return BuildParams(image="misc", version=version, command=misc_scripts[ctx_hyphen])
            if ctx_hyphen in available_images:
                return BuildParams(image=ctx_hyphen, version=version)

            # Try splitting hyphenated context parts to find a prefix match
            # e.g., "clang-rocm" with target "7.2.0" -> image="clang", version="rocm-7.2.0"
            parts = ctx_lower.split("-")
            if len(parts) >= 2:
                # Try progressively longer prefixes, longest first
                for split_at in range(len(parts) - 1, 0, -1):
                    prefix = "-".join(parts[:split_at])
                    remaining = "-".join(parts[split_at:])
                    prefix_version = (
                        " ".join(suffix_parts + [f"{remaining}-{self.target}"])
                        if suffix_parts
                        else f"{remaining}-{self.target}"
                    )
                    if prefix in misc_scripts:
                        return BuildParams(image="misc", version=prefix_version, command=misc_scripts[prefix])
                    if prefix in available_images:
                        return BuildParams(image=prefix, version=prefix_version)

        # Try the yaml filename (without .yaml extension)
        yaml_name = self.yaml_file.replace(".yaml", "").lower()
        if yaml_name in misc_scripts:
            return BuildParams(image="misc", version=self.target, command=misc_scripts[yaml_name])
        if yaml_name in available_images:
            return BuildParams(image=yaml_name, version=self.target)

        return None

    def get_build_command(self, available_images: set[str], misc_scripts: dict[str, str] | None = None) -> str | None:
        """Generate a gh CLI command to trigger the bespoke-build workflow."""
        params = self.get_build_params(available_images, misc_scripts)
        if not params:
            return None

        return (
            f"gh workflow run bespoke-build.yaml "
            f"-f image={params.image} -f version={params.version} -f command={params.command}"
        )


@dataclass
class AnalysisResult:
    """Result of analyzing YAML changes for build requirements."""

    requires_build: list[Addition] = field(default_factory=list)

    def has_build_requirements(self) -> bool:
        """Return True if any additions require building."""
        return len(self.requires_build) > 0


def parse_yaml_file(yaml_path: Path) -> dict[str, Any]:
    """Parse a YAML file safely."""
    with open(yaml_path, encoding="utf-8") as f:
        return yaml.load(f, Loader=ConfigSafeLoader) or {}


def extract_targets_with_context(
    node: Any, context: list[str], inherited_type: str | None = None
) -> list[tuple[list[str], str, str]]:
    """Extract all targets from a YAML node with their context and types.

    Returns list of (context, target, installer_type) tuples.
    """
    results: list[tuple[list[str], str, str]] = []

    if not isinstance(node, dict):
        return results

    current_type = node.get("type", inherited_type)

    if "targets" in node:
        targets = node["targets"]
        if isinstance(targets, list):
            for target in targets:
                if isinstance(target, str):
                    target_name = target
                elif isinstance(target, (int, float)):
                    target_name = str(target)
                elif isinstance(target, dict):
                    target_name = target.get("name", str(target))
                else:
                    continue

                if current_type:
                    results.append((context[:], target_name, current_type))

    for key, value in node.items():
        if key in ("targets", "type", "if"):
            continue
        if isinstance(value, dict):
            results.extend(extract_targets_with_context(value, context + [key], current_type))
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    results.extend(extract_targets_with_context(item, context + [key], current_type))

    return results


def get_all_targets_from_yaml(yaml_path: Path) -> set[tuple[tuple[str, ...], str]]:
    """Get all (context, target) pairs from a YAML file."""
    data = parse_yaml_file(yaml_path)
    targets_with_info = extract_targets_with_context(data, [])
    return {(tuple(ctx), target) for ctx, target, _ in targets_with_info}


def get_targets_with_types(yaml_path: Path) -> dict[tuple[tuple[str, ...], str], str]:
    """Get all targets with their installer types from a YAML file."""
    data = parse_yaml_file(yaml_path)
    targets_with_info = extract_targets_with_context(data, [])
    return {(tuple(ctx), target): inst_type for ctx, target, inst_type in targets_with_info}


def analyze_git_diff(yaml_dir: Path, base_ref: str = "origin/main") -> AnalysisResult:
    """Analyze git diff against a base ref to find YAML additions that require building."""
    yaml_dir = yaml_dir.resolve()

    diff_result = subprocess.run(
        ["git", "diff", "--name-only", base_ref, "--", str(yaml_dir)],
        capture_output=True,
        text=True,
        check=True,
    )

    changed_files = []
    for line in diff_result.stdout.strip().split("\n"):
        if line and line.endswith(".yaml") and "libraries.yaml" not in line:
            changed_files.append(Path(line).name)

    if not changed_files:
        return AnalysisResult()

    result = AnalysisResult()

    # Get git root to construct proper paths for git show
    git_root_result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=True,
    )
    git_root = Path(git_root_result.stdout.strip())
    yaml_rel_path = yaml_dir.relative_to(git_root)

    for yaml_file in changed_files:
        current_path = yaml_dir / yaml_file

        if not current_path.exists():
            continue

        current_targets = get_targets_with_types(current_path)

        try:
            base_content_result = subprocess.run(
                ["git", "show", f"{base_ref}:{yaml_rel_path}/{yaml_file}"],
                capture_output=True,
                text=True,
                check=True,
            )
            base_data = yaml.load(base_content_result.stdout, Loader=ConfigSafeLoader) or {}
            base_targets_list = extract_targets_with_context(base_data, [])
            base_targets = {(tuple(ctx), target) for ctx, target, _ in base_targets_list}
        except subprocess.CalledProcessError:
            base_targets = set()

        new_target_keys = set(current_targets.keys()) - base_targets

        for ctx_tuple, target in new_target_keys:
            installer_type = current_targets[(ctx_tuple, target)]
            if installer_type in BUILD_REQUIRED_TYPES:
                result.requires_build.append(
                    Addition(
                        yaml_file=yaml_file,
                        context=list(ctx_tuple),
                        target=target,
                        installer_type=installer_type,
                    )
                )

    return result


def format_result_for_pr_comment(
    result: AnalysisResult,
    available_images: set[str] | None = None,
    misc_scripts: dict[str, str] | None = None,
) -> str:
    """Format analysis result as a GitHub PR comment."""
    if not result.has_build_requirements():
        return ""

    if available_images is None:
        available_images = set()
    if misc_scripts is None:
        misc_scripts = {}

    lines = [
        "## Build Required",
        "",
        "The following additions require CE to build artifacts before deployment:",
        "",
    ]
    build_commands = []
    for addition in result.requires_build:
        build_cmd = addition.get_build_command(available_images, misc_scripts)
        if build_cmd:
            lines.append(f"- [ ] **{addition.yaml_file}**: `{addition.name}` (type: `{addition.installer_type}`)")
            build_commands.append(build_cmd)
        else:
            lines.append(f"- [ ] **{addition.yaml_file}**: `{addition.name}` (type: `{addition.installer_type}`)")

    lines.append("")
    lines.append(
        "Please ensure these have been built and uploaded to S3 before merging, or coordinate with the CE team."
    )

    if build_commands:
        lines.append("")
        lines.append("### Build Commands")
        lines.append("")
        lines.append("```bash")
        for cmd in build_commands:
            lines.append(cmd)
        lines.append("```")

    return "\n".join(lines)
