from pathlib import Path
from unittest.mock import MagicMock, PropertyMock, patch

import pytest
from lib.installable.installable import Installable
from lib.installation_context import InstallationContext


@pytest.fixture(name="fake_context")
def fake_context_fixture():
    return MagicMock(spec=InstallationContext)


def test_installable_sort(fake_context):
    ab_c = Installable(fake_context, dict(context=["a", "b"], name="c"))
    v1_2_3 = Installable(fake_context, dict(context=[], name="1.2.3"))
    v10_1 = Installable(fake_context, dict(context=[], name="10.1"))
    v10_1_alpha = Installable(fake_context, dict(context=[], name="10.1-alpha"))
    v10_2 = Installable(fake_context, dict(context=[], name="10.2"))
    assert sorted([v10_1, v10_1_alpha, ab_c, v1_2_3, v10_2], key=lambda x: x.sort_key) == [
        v1_2_3,
        v10_1,
        v10_1_alpha,
        v10_2,
        ab_c,
    ]


def test_is_installed_handles_permission_error_on_check_file(fake_context):
    """Test that is_installed() returns False when check_file raises PermissionError.

    This handles the case where CEFS mounts have restrictive permissions that prevent
    stat operations, allowing reinstallation to fix the issue.
    """
    # Setup: Create an installable with check_file set
    config = {"context": [], "name": "test-package", "check_file": "test.txt"}
    installable = Installable(fake_context, config)

    # Mock the destination property to return a Path
    mock_destination = MagicMock(spec=Path)
    type(fake_context).destination = PropertyMock(return_value=mock_destination)

    # Mock the path resolution to raise PermissionError on is_file()
    mock_path = MagicMock(spec=Path)
    mock_path.is_file.side_effect = PermissionError("[Errno 13] Permission denied")
    mock_destination.__truediv__.return_value = mock_path

    # Mock the logger to verify warning is logged
    with patch.object(installable, "_logger") as mock_logger:
        result = installable.is_installed()

        # Should return False to allow reinstallation
        assert result is False

        # Should log a warning about the permission issue
        mock_logger.warning.assert_called_once()
        warning_call = mock_logger.warning.call_args[0][0]
        assert "Permission denied" in warning_call
        assert "assuming not installed" in warning_call
