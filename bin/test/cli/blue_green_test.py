from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from click.testing import CliRunner
from lib.cli.blue_green import DeploymentCancelledException, blue_green_deploy
from lib.env import Config, Environment


class TestBlueGreenDeployCancellation(unittest.TestCase):
    """A cancelled deployment must not look like a successful one to automation.

    The release.yml workflow runs `ce ... blue-green deploy --skip-confirmation`; if the
    deployment is refused (e.g. the inactive ASG still has instances) and the CLI exits 0,
    the workflow reports success while the environment still serves the old build.
    """

    def setUp(self):
        self.runner = CliRunner()
        self.cfg = Config(env=Environment.STAGING)

    def _invoke(self, args):
        with (
            patch("lib.cli.blue_green.BlueGreenDeployment") as mock_deployment,
            patch("lib.cli.blue_green.are_you_sure", return_value=True),
        ):
            instance = MagicMock()
            instance.deploy.side_effect = DeploymentCancelledException(
                "Deployment cancelled: existing instances found with --skip-confirmation"
            )
            mock_deployment.return_value = instance
            return self.runner.invoke(blue_green_deploy, args, obj=self.cfg)

    def test_cancellation_with_skip_confirmation_exits_non_zero(self):
        result = self._invoke(["--skip-confirmation"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("existing instances found", result.output)

    def test_interactive_cancellation_exits_zero(self):
        # Without --skip-confirmation a cancellation is a deliberate human choice.
        result = self._invoke([])
        self.assertEqual(result.exit_code, 0)


if __name__ == "__main__":
    unittest.main()
