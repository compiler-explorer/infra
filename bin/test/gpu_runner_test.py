from __future__ import annotations

from unittest.mock import MagicMock, patch

from click.testing import CliRunner
from lib.cli.gpu_runner import gpu_runner


def test_gpu_runner_uploaddiscovery_uploads():
    mock_instance = MagicMock()
    mock_s3 = MagicMock()
    runner = CliRunner()

    with (
        patch("lib.cli.gpu_runner.GpuRunnerInstance") as mock_cls,
        patch("lib.cli.gpu_runner.get_remote_file") as mock_get_remote,
        patch("lib.cli.gpu_runner.boto3") as mock_boto3,
    ):
        mock_cls.instance.return_value = mock_instance
        mock_boto3.client.return_value = mock_s3

        def fake_get_remote(inst, remote, local):
            with open(local, "w") as f:
                f.write('{"compilers": []}')

        mock_get_remote.side_effect = fake_get_remote

        result = runner.invoke(gpu_runner, ["uploaddiscovery", "gpu", "gh-123"])
        assert result.exit_code == 0
        mock_s3.put_object.assert_called_once()
        call_kwargs = mock_s3.put_object.call_args[1]
        assert call_kwargs["Bucket"] == "compiler-explorer"
        assert call_kwargs["Key"] == "dist/discovery/gpu/gh-123.json"


def test_gpu_runner_uploaddiscovery_only_accepts_gpu_environment():
    runner = CliRunner()
    result = runner.invoke(gpu_runner, ["uploaddiscovery", "prod", "gh-123"])
    assert result.exit_code != 0
    assert "Invalid value" in result.output


def test_gpu_runner_status():
    mock_instance = MagicMock()
    mock_instance.status.return_value = "stopped"
    runner = CliRunner()

    with patch("lib.cli.gpu_runner.GpuRunnerInstance") as mock_cls:
        mock_cls.instance.return_value = mock_instance
        result = runner.invoke(gpu_runner, ["status"])
        assert result.exit_code == 0
        assert "GPU runner status: stopped" in result.output


def test_gpu_runner_stop():
    mock_instance = MagicMock()
    runner = CliRunner()

    with patch("lib.cli.gpu_runner.GpuRunnerInstance") as mock_cls:
        mock_cls.instance.return_value = mock_instance
        result = runner.invoke(gpu_runner, ["stop"])
        assert result.exit_code == 0
        mock_instance.stop.assert_called_once()
