"""Tests for build_check module."""

from __future__ import annotations

import tempfile
from pathlib import Path

from lib.build_check import (
    BUILD_REQUIRED_TYPES,
    Addition,
    AnalysisResult,
    extract_targets_with_context,
    format_result_for_pr_comment,
    get_all_targets_from_yaml,
    get_available_builder_images,
    get_targets_with_types,
    parse_yaml_file,
)


class TestBuildRequiredTypes:
    """Test that BUILD_REQUIRED_TYPES contains expected types."""

    def test_s3tarballs_requires_build(self):
        assert "s3tarballs" in BUILD_REQUIRED_TYPES

    def test_nightly_requires_build(self):
        assert "nightly" in BUILD_REQUIRED_TYPES

    def test_script_requires_build(self):
        assert "script" in BUILD_REQUIRED_TYPES


class TestExtractTargetsWithContext:
    """Test target extraction from YAML structures."""

    def test_simple_targets(self):
        node = {
            "type": "s3tarballs",
            "targets": ["1.0", "2.0"],
        }
        result = extract_targets_with_context(node, [])
        assert len(result) == 2
        assert ([], "1.0", "s3tarballs") in result
        assert ([], "2.0", "s3tarballs") in result

    def test_nested_context(self):
        node = {
            "compilers": {
                "erlang": {
                    "type": "s3tarballs",
                    "targets": ["24.1.6", "26.2.2"],
                }
            }
        }
        result = extract_targets_with_context(node, [])
        assert len(result) == 2
        assert (["compilers", "erlang"], "24.1.6", "s3tarballs") in result
        assert (["compilers", "erlang"], "26.2.2", "s3tarballs") in result

    def test_inherited_type(self):
        node = {
            "type": "s3tarballs",
            "gcc": {
                "targets": ["10.1.0", "11.1.0"],
            },
        }
        result = extract_targets_with_context(node, [])
        assert len(result) == 2
        assert (["gcc"], "10.1.0", "s3tarballs") in result
        assert (["gcc"], "11.1.0", "s3tarballs") in result

    def test_type_override(self):
        node = {
            "type": "s3tarballs",
            "gcc": {
                "targets": ["10.1.0"],
            },
            "tinygo": {
                "type": "tarballs",
                "targets": ["0.37.0"],
            },
        }
        result = extract_targets_with_context(node, [])
        assert (["gcc"], "10.1.0", "s3tarballs") in result
        assert (["tinygo"], "0.37.0", "tarballs") in result

    def test_dict_target_with_name(self):
        node = {
            "type": "nightly",
            "targets": [
                {"name": "trunk", "compiler_name": "go-trunk"},
            ],
        }
        result = extract_targets_with_context(node, [])
        assert len(result) == 1
        assert ([], "trunk", "nightly") in result

    def test_numeric_target(self):
        node = {
            "type": "s3tarballs",
            "targets": [1.0, 2.0],
        }
        result = extract_targets_with_context(node, [])
        assert len(result) == 2
        assert ([], "1.0", "s3tarballs") in result
        assert ([], "2.0", "s3tarballs") in result

    def test_list_of_dicts_in_hierarchy(self):
        node = {
            "cross": {
                "type": "s3tarballs",
                "arm": [
                    {"arch_prefix": "arm-unknown-linux-gnueabi", "targets": ["4.5.4"]},
                    {"arch_prefix": "arm-unknown-linux-gnueabihf", "targets": ["5.4.0"]},
                ],
            }
        }
        result = extract_targets_with_context(node, [])
        assert len(result) == 2
        assert (["cross", "arm"], "4.5.4", "s3tarballs") in result
        assert (["cross", "arm"], "5.4.0", "s3tarballs") in result


class TestParseYamlFile:
    """Test YAML file parsing."""

    def test_parse_simple_yaml(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("compilers:\n  erlang:\n    type: s3tarballs\n    targets:\n      - 24.1.6\n")
            f.flush()
            result = parse_yaml_file(Path(f.name))
            assert "compilers" in result
            assert result["compilers"]["erlang"]["type"] == "s3tarballs"


class TestGetAllTargetsFromYaml:
    """Test getting all targets from a YAML file."""

    def test_get_targets(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("compilers:\n  erlang:\n    type: s3tarballs\n    targets:\n      - 24.1.6\n      - 26.2.2\n")
            f.flush()
            result = get_all_targets_from_yaml(Path(f.name))
            assert (("compilers", "erlang"), "24.1.6") in result
            assert (("compilers", "erlang"), "26.2.2") in result


class TestGetTargetsWithTypes:
    """Test getting targets with their types."""

    def test_get_targets_with_types(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("compilers:\n  erlang:\n    type: s3tarballs\n    targets:\n      - 24.1.6\n")
            f.flush()
            result = get_targets_with_types(Path(f.name))
            assert result[(("compilers", "erlang"), "24.1.6")] == "s3tarballs"


class TestAddition:
    """Test Addition dataclass."""

    def test_name_property(self):
        addition = Addition(
            yaml_file="erlang.yaml",
            context=["compilers", "erlang"],
            target="24.1.6",
            installer_type="s3tarballs",
        )
        assert addition.name == "compilers/erlang 24.1.6"

    def test_name_empty_context(self):
        addition = Addition(
            yaml_file="test.yaml",
            context=[],
            target="1.0",
            installer_type="s3tarballs",
        )
        assert addition.name == "root 1.0"


class TestAnalysisResult:
    """Test AnalysisResult dataclass."""

    def test_has_build_requirements_empty(self):
        result = AnalysisResult()
        assert not result.has_build_requirements()

    def test_has_build_requirements_with_items(self):
        result = AnalysisResult(
            requires_build=[
                Addition(
                    yaml_file="test.yaml",
                    context=[],
                    target="1.0",
                    installer_type="s3tarballs",
                )
            ]
        )
        assert result.has_build_requirements()


class TestFormatResultForPrComment:
    """Test PR comment formatting."""

    def test_empty_result(self):
        result = AnalysisResult()
        output = format_result_for_pr_comment(result)
        assert not output

    def test_with_build_requirements(self):
        result = AnalysisResult(
            requires_build=[
                Addition(
                    yaml_file="erlang.yaml",
                    context=["compilers", "erlang"],
                    target="28.0",
                    installer_type="s3tarballs",
                )
            ]
        )
        output = format_result_for_pr_comment(result)
        assert "Build Required" in output
        assert "erlang.yaml" in output
        assert "compilers/erlang 28.0" in output
        assert "s3tarballs" in output
        assert "- [ ]" in output  # checkbox

    def test_with_build_commands(self):
        """Test that build commands are included when builder image is available."""
        result = AnalysisResult(
            requires_build=[
                Addition(
                    yaml_file="python.yaml",
                    context=["compilers", "python"],
                    target="3.14.0",
                    installer_type="s3tarballs",
                )
            ]
        )
        available_images = {"python", "gcc", "clang"}
        output = format_result_for_pr_comment(result, available_images)
        assert "Build Commands" in output
        assert "gh workflow run" in output
        assert "-f image=python" in output
        assert "-f version=3.14.0" in output


class TestBuildParams:
    """Test BuildParams and build URL generation."""

    def test_get_build_params_from_context(self):
        addition = Addition(
            yaml_file="python.yaml",
            context=["compilers", "python"],
            target="3.14.0",
            installer_type="s3tarballs",
        )
        available_images = {"python", "gcc", "clang"}
        params = addition.get_build_params(available_images)
        assert params is not None
        assert params.image == "python"
        assert params.version == "3.14.0"
        assert params.command == "build.sh"

    def test_get_build_params_from_yaml_filename(self):
        addition = Addition(
            yaml_file="micropython.yaml",
            context=["compilers", "micropython"],
            target="1.24.0",
            installer_type="s3tarballs",
        )
        available_images = {"micropython", "gcc"}
        params = addition.get_build_params(available_images)
        assert params is not None
        assert params.image == "micropython"

    def test_get_build_params_no_match(self):
        addition = Addition(
            yaml_file="erlang.yaml",
            context=["compilers", "erlang"],
            target="28.0",
            installer_type="s3tarballs",
        )
        available_images = {"python", "gcc", "clang"}
        params = addition.get_build_params(available_images)
        assert params is None

    def test_get_build_command(self):
        addition = Addition(
            yaml_file="clad.yaml",
            context=["compilers", "c++", "plugins", "clad"],
            target="2.1-clang-21.1.0",
            installer_type="s3tarballs",
        )
        available_images = {"clad", "gcc", "clang"}
        cmd = addition.get_build_command(available_images)
        assert cmd is not None
        assert "gh workflow run bespoke-build.yaml" in cmd
        assert "-f image=clad" in cmd
        assert "-f version=2.1-clang-21.1.0" in cmd


class TestGetAvailableBuilderImages:
    """Test extraction of builder images from workflow file."""

    def test_get_images_from_workflow(self):
        workflow_path = Path(".github/workflows/bespoke-build.yaml")
        if workflow_path.exists():
            images = get_available_builder_images(workflow_path)
            assert "gcc" in images
            assert "clang" in images
            assert len(images) > 10  # Should have many images

    def test_missing_workflow_returns_empty(self):
        images = get_available_builder_images(Path("/nonexistent/workflow.yaml"))
        assert images == set()


class TestMiscBuilderScripts:
    """Test misc builder script mapping."""

    def test_get_build_params_with_misc_script(self):
        """Test that misc builder scripts are correctly mapped."""
        addition = Addition(
            yaml_file="erlang.yaml",
            context=["compilers", "erlang"],
            target="28.0",
            installer_type="s3tarballs",
        )
        available_images = {"gcc", "clang", "misc"}
        misc_scripts = {"erlang": "build-erlang.sh"}
        params = addition.get_build_params(available_images, misc_scripts)
        assert params is not None
        assert params.image == "misc"
        assert params.version == "28.0"
        assert params.command == "build-erlang.sh"

    def test_get_build_command_with_misc_script(self):
        """Test that misc builder command is correctly generated."""
        addition = Addition(
            yaml_file="erlang.yaml",
            context=["compilers", "erlang"],
            target="28.0",
            installer_type="s3tarballs",
        )
        available_images = {"gcc", "clang", "misc"}
        misc_scripts = {"erlang": "build-erlang.sh"}
        cmd = addition.get_build_command(available_images, misc_scripts)
        assert cmd is not None
        assert "-f image=misc" in cmd
        assert "-f version=28.0" in cmd
        assert "-f command=build-erlang.sh" in cmd
