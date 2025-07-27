"""Tests for the notify module."""

import unittest
from unittest.mock import patch

from lib.notify import handle_notify, post, send_live_message


class TestNotify(unittest.TestCase):
    def test_post_dry_run_mode(self):
        """Test that post function logs in dry-run mode without making actual requests."""
        with self.assertLogs("lib.notify", level="INFO") as log:
            result = post("test/path", "fake_token", {"test": "data"}, dry_run=True)

            self.assertEqual(result, {})
            self.assertIn("[DRY RUN] Would post to test/path with data: {'test': 'data'}", log.output[0])

    def test_send_live_message_dry_run(self):
        """Test that send_live_message logs in dry-run mode."""
        with (
            self.assertLogs("lib.notify", level="INFO") as log,
            patch("lib.notify.should_send_comment_to_issue", return_value=True),
        ):
            send_live_message("123", "fake_token", dry_run=True)

            log_messages = "\n".join(log.output)
            self.assertIn("[DRY RUN] Would add 'live' label to issue #123", log_messages)
            self.assertIn("[DRY RUN] Would comment 'This is now live' on issue #123", log_messages)

    def test_handle_notify_dry_run(self):
        """Test that handle_notify processes correctly in dry-run mode."""
        mock_commits = [{"sha": "abc123"}]
        mock_pr = {"number": 456, "labels": []}

        with (
            patch("lib.notify.list_inbetween_commits", return_value=mock_commits),
            patch("lib.notify.get_linked_pr", return_value=mock_pr),
            patch("lib.notify.send_live_message") as mock_send,
            patch(
                "lib.notify.get_linked_issues",
                return_value={"data": {"repository": {"pullRequest": {"closingIssuesReferences": {"edges": []}}}}},
            ),
            self.assertLogs("lib.notify", level="INFO") as log,
        ):
            handle_notify("old_commit", "new_commit", "fake_token", dry_run=True)

            mock_send.assert_called_once_with(456, "fake_token", dry_run=True)
            log_messages = "\n".join(log.output)
            self.assertIn("[DRY RUN] Would notify PR #456", log_messages)

    def test_handle_notify_skips_empty_pr(self):
        """Test that handle_notify skips empty PR data."""
        mock_commits = [{"sha": "abc123"}]

        with (
            patch("lib.notify.list_inbetween_commits", return_value=mock_commits),
            patch("lib.notify.get_linked_pr", return_value={}),
            patch("lib.notify.send_live_message") as mock_send,
        ):
            handle_notify("old_commit", "new_commit", "fake_token", dry_run=False)

            mock_send.assert_not_called()


class TestBlueGreenVersionHelpers(unittest.TestCase):
    """Test the blue-green version tracking helper functions."""

    def test_get_commit_hash_for_version(self):
        """Test that we can convert version keys to commit hashes."""
        from lib.cli.blue_green import _get_commit_hash_for_version
        from lib.env import Config, Environment
        from lib.releases import Hash, Release, Version

        cfg = Config(env=Environment.PROD)

        # Mock releases data
        mock_release = Release(
            version=Version.from_string("12345"),
            branch="main",
            key="dist/gh/main/12345.tar.xz",
            info_key="dist/gh/main/12345.tar.xz.txt",
            size=1000,
            hash=Hash("abc123def456"),
            static_key=None,
        )

        with (
            patch("lib.cli.blue_green.get_releases", return_value=[mock_release]),
            patch("lib.cli.blue_green.release_for", return_value=mock_release),
        ):
            result = _get_commit_hash_for_version(cfg, "dist/gh/main/12345.tar.xz")
            self.assertEqual(result, "abc123def456")

    def test_get_commit_hash_for_version_not_found(self):
        """Test that we handle missing versions gracefully."""
        from lib.cli.blue_green import _get_commit_hash_for_version
        from lib.env import Config, Environment

        cfg = Config(env=Environment.PROD)

        with (
            patch("lib.cli.blue_green.get_releases", return_value=[]),
            patch("lib.cli.blue_green.release_for", return_value=None),
        ):
            result = _get_commit_hash_for_version(cfg, "nonexistent.tar.xz")
            self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
