import json
import subprocess
import unittest
from unittest.mock import MagicMock, patch

from click.testing import CliRunner
from lib.cli.workflows import (
    deploy_win,
    list_workflows,
    run_discovery,
    run_generic,
    status,
    wait_for_workflow_completion,
    watch,
)
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

    @patch("subprocess.run")
    def test_status_success_multi_repo(self, mock_run):
        # Mock responses for both repositories
        mock_run.side_effect = [
            MagicMock(
                stdout="completed\tsuccess\tInfra workflow\tmain\tpush\t123456\t1m\t2025-06-20T12:00:00Z\n",
                stderr="",
                returncode=0,
            ),
            MagicMock(
                stdout="completed\tsuccess\tCE workflow\tmain\tpush\t789012\t2m\t2025-06-20T12:01:00Z\n",
                stderr="",
                returncode=0,
            ),
        ]

        result = self.runner.invoke(
            status,
            ["--limit", "5"],
            obj=self.cfg,
        )

        self.assertEqual(result.exit_code, 0)
        self.assertIn("Recent workflow runs in infra:", result.output)
        self.assertIn("Recent workflow runs in compiler-explorer:", result.output)
        self.assertIn("Infra workflow", result.output)
        self.assertIn("CE workflow", result.output)

        # Should be called twice (once for each repo)
        self.assertEqual(mock_run.call_count, 2)

        # Check first call (infra)
        first_call_args = mock_run.call_args_list[0][0][0]
        self.assertIn("github.com/compiler-explorer/infra", first_call_args)

        # Check second call (compiler-explorer)
        second_call_args = mock_run.call_args_list[1][0][0]
        self.assertIn("github.com/compiler-explorer/compiler-explorer", second_call_args)

    @patch("subprocess.run")
    def test_status_success_single_repo(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout="completed\tsuccess\tTest workflow\tmain\tpush\t123456\t1m\t2025-06-20T12:00:00Z\n",
            stderr="",
            returncode=0,
        )

        result = self.runner.invoke(
            status,
            ["--repo", "infra", "--limit", "5"],
            obj=self.cfg,
        )

        self.assertEqual(result.exit_code, 0)
        self.assertIn("Recent workflow runs in infra:", result.output)
        self.assertIn("Test workflow", result.output)
        # Should not show compiler-explorer when specific repo is requested
        self.assertNotIn("Recent workflow runs in compiler-explorer:", result.output)

        # Should be called only once
        self.assertEqual(mock_run.call_count, 1)
        args = mock_run.call_args[0][0]
        self.assertIn("gh", args)
        self.assertIn("run", args)
        self.assertIn("list", args)
        self.assertIn("--limit", args)
        self.assertIn("5", args)
        self.assertIn("github.com/compiler-explorer/infra", args)

    @patch("subprocess.run")
    def test_status_with_filters(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", stderr="", returncode=0)

        result = self.runner.invoke(
            status,
            [
                "--repo",
                "compiler-explorer",
                "--workflow",
                "deploy-win.yml",
                "--status",
                "in_progress",
                "--branch",
                "main",
            ],
            obj=self.cfg,
        )

        self.assertEqual(result.exit_code, 0)
        args = mock_run.call_args[0][0]
        self.assertIn("github.com/compiler-explorer/compiler-explorer", args)
        self.assertIn("--workflow", args)
        self.assertIn("deploy-win.yml", args)
        self.assertIn("--status", args)
        self.assertIn("in_progress", args)
        self.assertIn("--branch", args)
        self.assertIn("main", args)

    @patch("subprocess.run")
    def test_status_no_results_multi_repo(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", stderr="", returncode=0)

        result = self.runner.invoke(status, obj=self.cfg)

        self.assertEqual(result.exit_code, 0)
        self.assertIn("No workflow runs found in infra", result.output)
        self.assertIn("No workflow runs found in compiler-explorer", result.output)
        # Should be called twice (once for each repo)
        self.assertEqual(mock_run.call_count, 2)

    @patch("subprocess.run")
    def test_watch_success(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout="* main Test workflow · 123456\nTriggered via push\n\nJOBS\n* test-job (ID 789)\n",
            stderr="",
            returncode=0,
        )

        result = self.runner.invoke(
            watch,
            ["123456"],
            obj=self.cfg,
        )

        self.assertEqual(result.exit_code, 0)
        self.assertIn("Test workflow", result.output)
        self.assertIn("test-job", result.output)

        args = mock_run.call_args[0][0]
        self.assertIn("gh", args)
        self.assertIn("run", args)
        self.assertIn("view", args)
        self.assertIn("123456", args)
        self.assertIn("github.com/compiler-explorer/infra", args)

    @patch("subprocess.run")
    def test_watch_with_options(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", stderr="", returncode=0)

        result = self.runner.invoke(
            watch,
            ["123456", "--repo", "compiler-explorer", "--job", "456789"],
            obj=self.cfg,
        )

        self.assertEqual(result.exit_code, 0)
        args = mock_run.call_args[0][0]
        self.assertIn("github.com/compiler-explorer/compiler-explorer", args)
        self.assertIn("--job", args)
        self.assertIn("456789", args)

    @patch("time.sleep")
    @patch("subprocess.run")
    def test_run_discovery_with_wait(self, mock_run, mock_sleep):
        # First call triggers workflow, second gets the list, third+ check status
        mock_run.side_effect = [
            MagicMock(stdout="", stderr="", returncode=0),  # trigger workflow
            MagicMock(stdout=json.dumps([{"databaseId": 12345, "status": "queued"}])),  # list runs
            MagicMock(stdout=json.dumps({"status": "in_progress", "conclusion": None})),  # first status check
            MagicMock(stdout=json.dumps({"status": "completed", "conclusion": "success"})),  # final status
        ]

        result = self.runner.invoke(
            run_discovery,
            ["gh-12345", "--wait"],
            obj=self.cfg,
        )

        self.assertEqual(result.exit_code, 0)
        self.assertIn("Workflow triggered successfully", result.output)
        self.assertIn("Waiting for compiler-discovery.yml", result.output)
        self.assertIn("Monitoring run 12345", result.output)
        self.assertIn("Workflow completed successfully!", result.output)

    @patch("time.sleep")
    @patch("subprocess.run")
    def test_deploy_win_with_wait_failure(self, mock_run, mock_sleep):
        # First call triggers workflow, second gets the list, third checks status (failed)
        mock_run.side_effect = [
            MagicMock(stdout="", stderr="", returncode=0),  # trigger workflow
            MagicMock(stdout=json.dumps([{"databaseId": 67890, "status": "completed"}])),  # list runs
            MagicMock(stdout=json.dumps({"status": "completed", "conclusion": "failure"})),  # status check
        ]

        result = self.runner.invoke(
            deploy_win,
            ["gh-12345", "--wait"],
            obj=self.cfg,
        )

        self.assertEqual(result.exit_code, 1)
        self.assertIn("Workflow triggered successfully", result.output)
        self.assertIn("Waiting for deploy-win.yml", result.output)
        self.assertIn("Workflow completed with conclusion: failure", result.output)

    @patch("time.sleep")
    @patch("subprocess.run")
    def test_run_generic_with_wait(self, mock_run, mock_sleep):
        # First call triggers workflow, second gets the list, third checks status
        mock_run.side_effect = [
            MagicMock(stdout="", stderr="", returncode=0),  # trigger workflow
            MagicMock(stdout=json.dumps([{"databaseId": 11111, "status": "completed"}])),  # list runs
            MagicMock(stdout=json.dumps({"status": "completed", "conclusion": "success"})),  # status check
        ]

        result = self.runner.invoke(
            run_generic,
            ["infra", "test.yml", "-f", "param=value", "--wait"],
            obj=self.cfg,
        )

        self.assertEqual(result.exit_code, 0)
        self.assertIn("Workflow triggered successfully", result.output)
        self.assertIn("Waiting for test.yml", result.output)
        self.assertIn("Workflow completed successfully!", result.output)

    @patch("time.sleep")
    @patch("subprocess.run")
    def test_wait_for_workflow_completion_no_runs(self, mock_run, mock_sleep):
        # Mock empty list of runs
        mock_run.return_value = MagicMock(stdout=json.dumps([]))

        # Call the function directly
        wait_for_workflow_completion("test-repo", "test.yml")

        # Should handle gracefully when no runs found
        mock_run.assert_called_once()

    @patch("time.sleep")
    @patch("subprocess.run")
    def test_wait_for_workflow_completion_cancelled(self, mock_run, mock_sleep):
        # Test handling of cancelled workflow
        mock_run.side_effect = [
            MagicMock(stdout=json.dumps([{"databaseId": 99999, "status": "in_progress"}])),  # list runs
            MagicMock(stdout=json.dumps({"status": "completed", "conclusion": "cancelled"})),  # status check
        ]

        # Call the function directly (doesn't exit for cancelled)
        wait_for_workflow_completion("test-repo", "test.yml")

        # Should complete without error for cancelled workflows
        self.assertEqual(mock_run.call_count, 2)
