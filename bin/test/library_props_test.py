import pytest
from lib.library_props import (
    extract_library_id_from_github_url,
    find_existing_library_by_github_url,
    generate_all_libraries_properties,
    generate_library_path,
    generate_single_library_properties,
    generate_standalone_library_properties,
    merge_properties,
    parse_properties_file,
    update_library_in_properties,
    version_to_id,
)


def test_generate_library_path():
    """Test library path generation."""
    assert generate_library_path("fmt", "10.2.1") == "/opt/compiler-explorer/libs/fmt/10.2.1/include"
    assert generate_library_path("json", "3.11.3") == "/opt/compiler-explorer/libs/json/3.11.3/include"
    # Test with target_prefix
    assert (
        generate_library_path("nlohmann_json", "3.11.3", "v")
        == "/opt/compiler-explorer/libs/nlohmann_json/v3.11.3/include"
    )
    assert generate_library_path("test", "1.0.0", "") == "/opt/compiler-explorer/libs/test/1.0.0/include"


def test_version_to_id():
    """Test version string to ID conversion."""
    assert version_to_id("10.2.1") == "1021"
    assert version_to_id("3.11.3") == "3113"
    assert version_to_id("1.0.0") == "100"
    assert version_to_id("20.01.5") == "20015"


def test_extract_library_id_from_github_url():
    """Test extracting library ID from GitHub URLs."""
    assert extract_library_id_from_github_url("https://github.com/fmtlib/fmt") == "fmt"
    assert extract_library_id_from_github_url("https://github.com/nlohmann/json") == "json"
    assert extract_library_id_from_github_url("https://github.com/microsoft/vcpkg") == "vcpkg"
    assert extract_library_id_from_github_url("https://github.com/google/googletest") == "googletest"

    # Test with hyphens converted to underscores
    assert extract_library_id_from_github_url("https://github.com/gabime/spdlog") == "spdlog"
    assert extract_library_id_from_github_url("https://github.com/pybind/pybind11") == "pybind11"
    assert extract_library_id_from_github_url("https://github.com/someone/my-library") == "my_library"


def test_extract_library_id_from_github_url_invalid():
    """Test error handling for invalid GitHub URLs."""
    with pytest.raises(ValueError, match="URL must be a GitHub URL"):
        extract_library_id_from_github_url("https://gitlab.com/fmtlib/fmt")

    with pytest.raises(ValueError, match="Invalid GitHub URL format"):
        extract_library_id_from_github_url("https://github.com/")

    with pytest.raises(ValueError, match="Invalid GitHub URL format"):
        extract_library_id_from_github_url("https://github.com/user")


def test_parse_properties_file():
    """Test parsing properties file content."""
    content = """# Comment line
libs=fmt:json:boost

libs.fmt.name=fmt
libs.fmt.url=https://github.com/fmtlib/fmt
libs.fmt.versions=1021

# Another comment
libs.json.name=json
libs.json.versions=3113
"""

    result = parse_properties_file(content)

    assert result["libs"] == "fmt:json:boost"
    assert result["libs.fmt.name"] == "fmt"
    assert result["libs.fmt.url"] == "https://github.com/fmtlib/fmt"
    assert result["libs.fmt.versions"] == "1021"
    assert result["libs.json.name"] == "json"
    assert result["libs.json.versions"] == "3113"


def test_generate_single_library_properties_specific_version():
    """Test generating properties for a single library version."""
    lib_info = {"type": "github", "repo": "fmtlib/fmt", "targets": ["10.0.0", "10.1.1", "10.2.1"]}

    result = generate_single_library_properties("fmt", lib_info, specific_version="10.2.1")

    assert result["versions.1021.version"] == "10.2.1"
    assert result["versions.1021.path"] == "/opt/compiler-explorer/libs/fmt/10.2.1/include"
    # Should not have library-level properties for specific version
    assert "name" not in result
    assert "url" not in result


def test_generate_single_library_properties_all_versions():
    """Test generating properties for all versions of a library."""
    lib_info = {"type": "github", "repo": "fmtlib/fmt", "targets": ["10.0.0", "10.1.1", "10.2.1"]}

    result = generate_single_library_properties("fmt", lib_info)

    # Should have library-level properties
    assert result["name"] == "fmt"
    assert result["url"] == "https://github.com/fmtlib/fmt"
    assert result["versions"] == "1000:1011:1021"

    # Should have version-specific properties
    assert result["versions.1000.version"] == "10.0.0"
    assert result["versions.1000.path"] == "/opt/compiler-explorer/libs/fmt/10.0.0/include"
    assert result["versions.1021.version"] == "10.2.1"
    assert result["versions.1021.path"] == "/opt/compiler-explorer/libs/fmt/10.2.1/include"


def test_generate_single_library_properties_package_install():
    """Test that package_install libraries don't get paths."""
    lib_info = {"type": "github", "repo": "nlohmann/json", "targets": ["3.11.3"], "package_install": True}

    result = generate_single_library_properties("json", lib_info, specific_version="3.11.3")

    assert result["versions.3113.version"] == "3.11.3"
    # Should not have path for package_install libraries
    assert "versions.3113.path" not in result


def test_generate_single_library_properties_version_not_found():
    """Test error when requested version is not found."""
    lib_info = {"type": "github", "repo": "fmtlib/fmt", "targets": ["10.0.0", "10.1.1"]}

    with pytest.raises(ValueError, match="Version '10.2.1' not found for library 'fmt'"):
        generate_single_library_properties("fmt", lib_info, specific_version="10.2.1")


def test_generate_all_libraries_properties():
    """Test generating properties for multiple libraries."""
    cpp_libraries = {
        "fmt": {"type": "github", "repo": "fmtlib/fmt", "targets": ["10.2.1"]},
        "json": {"type": "github", "repo": "nlohmann/json", "targets": ["3.11.3"], "package_install": True},
        # These should be skipped
        "nightly": {"some": "config"},
        "manual_lib": {"build_type": "manual", "targets": ["1.0.0"]},
    }

    result = generate_all_libraries_properties(cpp_libraries)

    # Should start with libs= line
    assert result.startswith("libs=fmt:json\n\n")

    # Should contain fmt properties
    assert "libs.fmt.name=fmt" in result
    assert "libs.fmt.url=https://github.com/fmtlib/fmt" in result
    assert "libs.fmt.versions.1021.version=10.2.1" in result
    assert "libs.fmt.versions.1021.path=/opt/compiler-explorer/libs/fmt/10.2.1/include" in result

    # Should contain json properties but no path (package_install)
    assert "libs.json.name=json" in result
    assert "libs.json.versions.3113.version=3.11.3" in result
    assert "libs.json.versions.3113.path=" not in result

    # Should not contain nightly or manual_lib
    assert "nightly" not in result
    assert "manual_lib" not in result


def test_generate_standalone_library_properties():
    """Test generating standalone properties for a library."""
    lib_props = {
        "versions.1021.version": "10.2.1",
        "versions.1021.path": "/opt/compiler-explorer/libs/fmt/10.2.1/include",
    }

    result = generate_standalone_library_properties("fmt", lib_props, specific_version="10.2.1")

    lines = result.split("\n")
    assert lines[0] == "libs=fmt"
    assert not lines[1]
    assert "libs.fmt.versions.1021.path=/opt/compiler-explorer/libs/fmt/10.2.1/include" in lines
    assert "libs.fmt.versions.1021.version=10.2.1" in lines


def test_update_library_in_properties_with_version_id():
    """Test update_library_in_properties with explicit update_version_id parameter."""
    existing_content = """libs=fmt:json

libs.fmt.name=fmt
libs.fmt.url=https://github.com/fmtlib/fmt
libs.fmt.versions=1000:1011

libs.fmt.versions.1000.version=10.0.0
libs.fmt.versions.1000.path=/opt/compiler-explorer/libs/fmt/10.0.0/include
libs.fmt.versions.1011.version=10.1.1
libs.fmt.versions.1011.path=/opt/compiler-explorer/libs/fmt/10.1.1/include
"""

    # Properties for a new version
    lib_props = {
        "versions.1021.version": "10.2.1",
        "versions.1021.path": "/opt/compiler-explorer/libs/fmt/10.2.1/include",
    }

    # Call with explicit version ID parameter
    result = update_library_in_properties(existing_content, "fmt", lib_props, update_version_id="1021")

    # Should add the new version to the versions list
    assert "libs.fmt.versions=1000:1011:1021" in result
    # Should include the new version properties
    assert "libs.fmt.versions.1021.version=10.2.1" in result
    assert "libs.fmt.versions.1021.path=/opt/compiler-explorer/libs/fmt/10.2.1/include" in result


def test_generate_single_library_properties_with_link_properties():
    """Test that sharedliblink and staticliblink are included in properties."""
    lib_info = {
        "type": "github",
        "repo": "fmtlib/fmt",
        "targets": ["10.2.1"],
        "sharedliblink": ["fmt", "fmtd"],
        "staticliblink": ["fmts", "fmtsd"],
    }

    result = generate_single_library_properties("fmt", lib_info)

    # Should have library-level properties including link properties
    assert result["name"] == "fmt"
    assert result["url"] == "https://github.com/fmtlib/fmt"
    assert result["liblink"] == "fmt:fmtd"
    assert result["staticliblink"] == "fmts:fmtsd"
    assert result["versions"] == "1021"


def test_generate_all_libraries_properties_with_link_properties():
    """Test that sharedliblink and staticliblink are included in all libraries output."""
    cpp_libraries = {
        "fmt": {
            "type": "github",
            "repo": "fmtlib/fmt",
            "targets": ["10.2.1"],
            "sharedliblink": ["fmt"],
            "staticliblink": ["fmts"],
        }
    }

    result = generate_all_libraries_properties(cpp_libraries)

    # Should contain the link properties
    assert "libs.fmt.liblink=fmt" in result
    assert "libs.fmt.staticliblink=fmts" in result


def test_find_existing_library_by_github_url():
    """Test finding existing libraries by GitHub URL."""
    cpp_libraries = {
        "fmt": {"repo": "fmtlib/fmt", "type": "github"},
        "json": {"repo": "nlohmann/json", "type": "github"},
        "nightly": {"some_lib": {"repo": "some/nightly-lib", "type": "github"}},
    }

    # Should find existing libraries
    assert find_existing_library_by_github_url(cpp_libraries, "https://github.com/fmtlib/fmt") == "fmt"
    assert find_existing_library_by_github_url(cpp_libraries, "https://github.com/nlohmann/json") == "json"

    # Should not match libraries nested inside the nightly subsection
    assert find_existing_library_by_github_url(cpp_libraries, "https://github.com/some/nightly-lib") is None

    # Should return None for non-existent libraries
    assert find_existing_library_by_github_url(cpp_libraries, "https://github.com/nonexistent/repo") is None

    # Should return None for non-GitHub URLs
    assert find_existing_library_by_github_url(cpp_libraries, "https://gitlab.com/fmtlib/fmt") is None


def test_generate_single_library_properties_with_target_prefix():
    """Test generating properties with target_prefix for version tags."""
    lib_info = {"type": "github", "repo": "nlohmann/json", "targets": ["3.11.3"], "target_prefix": "v"}

    result = generate_single_library_properties("nlohmann_json", lib_info, specific_version="3.11.3")

    assert result["versions.3113.version"] == "3.11.3"
    assert result["versions.3113.path"] == "/opt/compiler-explorer/libs/nlohmann_json/v3.11.3/include"


def test_generate_all_libraries_properties_with_target_prefix():
    """Test generating properties for libraries with target_prefix."""
    cpp_libraries = {
        "nlohmann_json": {"type": "github", "repo": "nlohmann/json", "targets": ["3.11.3"], "target_prefix": "v"}
    }

    result = generate_all_libraries_properties(cpp_libraries)

    assert "libs.nlohmann_json.versions.3113.path=/opt/compiler-explorer/libs/nlohmann_json/v3.11.3/include" in result


def test_update_library_preserves_final_newline():
    """Test that updating library properties preserves the original file's final newline."""
    # Content with final newline
    existing_content_with_newline = """libs=fmt

libs.fmt.name=fmt
libs.fmt.url=https://github.com/fmtlib/fmt
libs.fmt.versions=1000
"""

    # Content without final newline
    existing_content_without_newline = """libs=fmt

libs.fmt.name=fmt
libs.fmt.url=https://github.com/fmtlib/fmt
libs.fmt.versions=1000"""

    lib_props = {
        "versions.1021.version": "10.2.1",
        "versions.1021.path": "/opt/compiler-explorer/libs/fmt/10.2.1/include",
    }

    # Test with newline - should preserve it
    result_with_newline = update_library_in_properties(existing_content_with_newline, "fmt", lib_props, "1021")
    assert result_with_newline.endswith("\n"), "Should preserve final newline when original had one"

    # Test without newline - should preserve that too
    result_without_newline = update_library_in_properties(existing_content_without_newline, "fmt", lib_props, "1021")
    assert not result_without_newline.endswith("\n"), "Should preserve no final newline when original didn't have one"


def test_merge_properties_preserves_final_newline():
    """Test that merging properties preserves the original file's final newline."""
    # Existing content with final newline
    existing_with_newline = """libs=fmt

libs.fmt.name=fmt
libs.fmt.versions=1000
"""

    # New content to merge
    new_content = """libs=json

libs.json.name=json
libs.json.versions=3113
"""

    result = merge_properties(existing_with_newline, new_content)
    assert result.endswith("\n"), "Should preserve final newline when original had one"

    # Test without final newline
    existing_without_newline = existing_with_newline.rstrip("\n")
    result = merge_properties(existing_without_newline, new_content)
    assert not result.endswith("\n"), "Should preserve no final newline when original didn't have one"


def test_update_library_preserves_existing_name_and_url():
    """Test that updating library properties preserves existing name and url values."""
    existing_content = """libs=fmt

libs.fmt.name=Custom FMT Library
libs.fmt.url=https://example.com/custom-fmt
libs.fmt.versions=1000
libs.fmt.versions.1000.version=10.0.0
libs.fmt.versions.1000.path=/opt/compiler-explorer/libs/fmt/10.0.0/include
"""

    # Properties that include name and url (which should be ignored if they exist)
    lib_props = {
        "name": "fmt",
        "url": "https://github.com/fmtlib/fmt",
        "versions": "1000:1021",
        "versions.1021.version": "10.2.1",
        "versions.1021.path": "/opt/compiler-explorer/libs/fmt/10.2.1/include",
    }

    result = update_library_in_properties(existing_content, "fmt", lib_props, update_version_id="1021")

    # Should preserve the existing custom name and url
    assert "libs.fmt.name=Custom FMT Library" in result
    assert "libs.fmt.url=https://example.com/custom-fmt" in result

    # Should NOT contain the new values from lib_props
    assert "libs.fmt.name=fmt\n" not in result
    assert "libs.fmt.url=https://github.com/fmtlib/fmt" not in result

    # Should still update the versions list and add new version properties
    assert "libs.fmt.versions=1000:1021" in result
    assert "libs.fmt.versions.1021.version=10.2.1" in result
    assert "libs.fmt.versions.1021.path=/opt/compiler-explorer/libs/fmt/10.2.1/include" in result
