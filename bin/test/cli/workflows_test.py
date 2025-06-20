import subprocess
import unittest
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from lib.cli.workflows import deploy_win, list_workflows, run_discovery, run_generic
from lib.env import Config, Environment


class TestWorkflowsCommands(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()
        self.cfg = Config(env=Environment.STAGING)

    def test_list_workflows(self):
        result = self.runner.invoke(list_workflows, obj=self.cfg)
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Workflows in compiler-explorer/infra:", result.output)
        self.assertIn("compiler-discovery.yml", result.output)
        self.assertIn("win-lib-build.yaml", result.output)
        self.assertIn("Workflows in compiler-explorer/compiler-explorer:", result.output)
        self.assertIn("deploy-win.yml", result.output)

    @patch("subprocess.run")
    def test_run_discovery_success(self, mock_run):
        mock_run.return_value = MagicMock(stdout="Workflow triggered", stderr="", returncode=0)

        result = self.runner.invoke(
            run_discovery,
            ["123"],
            obj=self.cfg,
        )

        self.assertEqual(result.exit_code, 0)
        self.assertIn("Triggering compiler discovery", result.output)
        self.assertIn("Workflow triggered successfully", result.output)

        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        self.assertEqual(args[0], "gh")
        self.assertEqual(args[1], "workflow")
        self.assertEqual(args[2], "run")
        self.assertEqual(args[3], "compiler-discovery.yml")
        self.assertIn("--field", args)
        self.assertIn("environment=staging", args)
        self.assertIn("branch=main", args)
        self.assertIn("buildnumber=123", args)

    @patch("subprocess.run")
    def test_run_discovery_with_defaults(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", stderr="", returncode=0)

        result = self.runner.invoke(
            run_discovery,
            ["gh-12345"],
            obj=self.cfg,
        )

        self.assertEqual(result.exit_code, 0)
        args = mock_run.call_args[0][0]
        self.assertIn("environment=staging", args)  # default
        self.assertIn("branch=main", args)  # default
        self.assertIn("buildnumber=gh-12345", args)

    @patch("subprocess.run")
    def test_run_discovery_with_skip_remote_checks(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", stderr="", returncode=0)

        result = self.runner.invoke(
            run_discovery,
            [
                "456",
                "--environment",
                "prod",
                "--branch",
                "release",
                "--skip-remote-checks",
                "check1,check2",
            ],
            obj=self.cfg,
        )

        self.assertEqual(result.exit_code, 0)
        args = mock_run.call_args[0][0]
        self.assertIn("skip_remote_checks=check1,check2", args)

    def test_run_discovery_dry_run(self):
        result = self.runner.invoke(
            run_discovery,
            ["789", "--environment", "beta", "--branch", "develop", "--dry-run"],
            obj=self.cfg,
        )

        self.assertEqual(result.exit_code, 0)
        self.assertIn("gh workflow run compiler-discovery.yml", result.output)
        self.assertIn("environment=beta", result.output)
        self.assertIn("branch=develop", result.output)
        self.assertIn("buildnumber=789", result.output)

    @patch("subprocess.run")
    def test_run_discovery_failure(self, mock_run):
        mock_run.side_effect = subprocess.CalledProcessError(1, "gh", stderr="Authentication failed")

        result = self.runner.invoke(
            run_discovery,
            ["999"],
            obj=self.cfg,
        )

        self.assertEqual(result.exit_code, 1)
        self.assertIn("Failed to trigger workflow", result.output)

    def test_run_discovery_missing_buildnumber(self):
        result = self.runner.invoke(run_discovery, obj=self.cfg)
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("Missing argument 'BUILDNUMBER'", result.output)

    @patch("subprocess.run")
    def test_deploy_win_success(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", stderr="", returncode=0)

        result = self.runner.invoke(
            deploy_win,
            ["gh-12345"],
            obj=self.cfg,
        )

        self.assertEqual(result.exit_code, 0)
        self.assertIn("Triggering Windows deployment", result.output)
        
        args = mock_run.call_args[0][0]
        self.assertIn("deploy-win.yml", args)
        self.assertIn("buildnumber=gh-12345", args)
        self.assertIn("branch=main", args)
        self.assertIn("github.com/compiler-explorer/compiler-explorer", args)

    def test_deploy_win_dry_run(self):
        result = self.runner.invoke(
            deploy_win,
            ["gh-12345", "--branch", "release", "--dry-run"],
            obj=self.cfg,
        )

        self.assertEqual(result.exit_code, 0)
        self.assertIn("gh workflow run deploy-win.yml", result.output)
        self.assertIn("buildnumber=gh-12345", result.output)
        self.assertIn("branch=release", result.output)
        self.assertIn("github.com/compiler-explorer/compiler-explorer", result.output)

    @patch("subprocess.run")
    def test_run_generic_success(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", stderr="", returncode=0)

        result = self.runner.invoke(
            run_generic,
            ["compiler-explorer", "deploy-win.yml", "-f", "buildnumber=gh-12345", "-f", "branch=main"],
            obj=self.cfg,
        )

        self.assertEqual(result.exit_code, 0)
        self.assertIn("Triggering workflow deploy-win.yml", result.output)
        
        args = mock_run.call_args[0][0]
        self.assertIn("deploy-win.yml", args)
        self.assertIn("buildnumber=gh-12345", args)
        self.assertIn("branch=main", args)
        self.assertIn("github.com/compiler-explorer/compiler-explorer", args)

    def test_run_generic_dry_run(self):
        result = self.runner.invoke(
            run_generic,
            ["infra", "test.yml", "-f", "param1=value1", "-f", "param2=value2", "--dry-run"],
            obj=self.cfg,
        )

        self.assertEqual(result.exit_code, 0)
        self.assertIn("gh workflow run test.yml", result.output)
        self.assertIn("param1=value1", result.output)
        self.assertIn("param2=value2", result.output)
        self.assertIn("github.com/compiler-explorer/infra", result.output)