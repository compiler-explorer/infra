import pytest
from lib.cli.fortran_libraries import (
    generate_all_fortran_libraries_properties,
    generate_single_fortran_library_properties,
    generate_standalone_fortran_library_properties,
)


def test_generate_single_fortran_library_properties_specific_version():
    """Test generating properties for a single Fortran library version."""
    lib_info = {
        "type": "github",
        "repo": "jacobwilliams/json-fortran",
        "build_type": "fpm",
        "targets": ["8.2.0", "8.3.0"],
    }

    result = generate_single_fortran_library_properties("json_fortran", lib_info, specific_version="8.2.0")

    assert result["versions.820.version"] == "8.2.0"
    assert result["versions.820.path"] == "/opt/compiler-explorer/libs/fortran/json_fortran/8.2.0"
    # Should not have library-level properties for specific version
    assert "name" not in result
    assert "url" not in result


def test_generate_single_fortran_library_properties_all_versions():
    """Test generating properties for all versions of a Fortran library."""
    lib_info = {
        "type": "github",
        "repo": "jacobwilliams/json-fortran",
        "build_type": "fpm",
        "targets": ["8.2.0", "8.3.0"],
    }

    result = generate_single_fortran_library_properties("json_fortran", lib_info)

    # Should have library-level properties
    assert result["name"] == "json_fortran"
    assert result["url"] == "https://github.com/jacobwilliams/json-fortran"
    assert result["versions"] == "820:830"

    # Should have version-specific properties
    assert result["versions.820.version"] == "8.2.0"
    assert result["versions.820.path"] == "/opt/compiler-explorer/libs/fortran/json_fortran/8.2.0"
    assert result["versions.830.version"] == "8.3.0"
    assert result["versions.830.path"] == "/opt/compiler-explorer/libs/fortran/json_fortran/8.3.0"


def test_generate_single_fortran_library_properties_with_target_prefix():
    """Test generating properties with target_prefix for version tags."""
    lib_info = {
        "type": "github",
        "repo": "fortran-lang/http-client",
        "build_type": "fpm",
        "targets": ["0.1.0"],
        "target_prefix": "v",
    }

    result = generate_single_fortran_library_properties("http_client", lib_info, specific_version="0.1.0")

    assert result["versions.010.version"] == "0.1.0"
    assert result["versions.010.path"] == "/opt/compiler-explorer/libs/fortran/http_client/v0.1.0"


def test_generate_single_fortran_library_properties_version_not_found():
    """Test error when requested version is not found."""
    lib_info = {
        "type": "github",
        "repo": "jacobwilliams/json-fortran",
        "build_type": "fpm",
        "targets": ["8.2.0", "8.3.0"],
    }

    with pytest.raises(ValueError, match="Version '9.0.0' not found for library 'json_fortran'"):
        generate_single_fortran_library_properties("json_fortran", lib_info, specific_version="9.0.0")


def test_generate_all_fortran_libraries_properties():
    """Test generating properties for multiple Fortran libraries."""
    fortran_libraries = {
        "json_fortran": {
            "type": "github",
            "repo": "jacobwilliams/json-fortran",
            "build_type": "fpm",
            "targets": ["8.3.0"],
        },
        "http_client": {
            "type": "github",
            "repo": "fortran-lang/http-client",
            "build_type": "fpm",
            "targets": ["0.1.0"],
            "target_prefix": "v",
        },
        # These should be skipped
        "nightly": {"some": "config"},
        "manual_lib": {"build_type": "manual", "targets": ["1.0.0"]},
    }

    result = generate_all_fortran_libraries_properties(fortran_libraries)

    # Should start with libs.fortran= line
    assert result.startswith("libs.fortran=json_fortran:http_client\n\n")

    # Should contain json_fortran properties
    assert "libs.fortran.json_fortran.name=json_fortran" in result
    assert "libs.fortran.json_fortran.url=https://github.com/jacobwilliams/json-fortran" in result
    assert "libs.fortran.json_fortran.versions.830.version=8.3.0" in result
    assert "libs.fortran.json_fortran.versions.830.path=/opt/compiler-explorer/libs/fortran/json_fortran/8.3.0" in result

    # Should contain http_client properties with target_prefix
    assert "libs.fortran.http_client.name=http_client" in result
    assert "libs.fortran.http_client.versions.010.version=0.1.0" in result
    assert "libs.fortran.http_client.versions.010.path=/opt/compiler-explorer/libs/fortran/http_client/v0.1.0" in result

    # Should not contain nightly or manual_lib
    assert "nightly" not in result
    assert "manual_lib" not in result


def test_generate_standalone_fortran_library_properties():
    """Test generating standalone properties for a Fortran library."""
    lib_props = {
        "versions.830.version": "8.3.0",
        "versions.830.path": "/opt/compiler-explorer/libs/fortran/json_fortran/8.3.0",
    }

    result = generate_standalone_fortran_library_properties("json_fortran", lib_props, specific_version="8.3.0")

    lines = result.split("\n")
    assert lines[0] == "libs.fortran=json_fortran"
    assert lines[1] == ""
    assert "libs.fortran.json_fortran.versions.830.path=/opt/compiler-explorer/libs/fortran/json_fortran/8.3.0" in lines
    assert "libs.fortran.json_fortran.versions.830.version=8.3.0" in lines