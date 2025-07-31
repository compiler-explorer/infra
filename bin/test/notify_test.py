"""Tests for the notify module."""

import unittest
from unittest.mock import patch

from lib.notify import handle_notify, post, send_live_message


class TestNotify(unittest.TestCase):
    def test_post_dry_run_mode(self):
        """Test that post function prints in dry-run mode without making actual requests."""
        with patch("builtins.print") as mock_print:
            result = post("test/path", "fake_token", {"test": "data"}, dry_run=True)

            self.assertEqual(result, {})
            mock_print.assert_called_once_with("[DRY RUN] Would post to test/path with data: {'test': 'data'}")

    def test_send_live_message_dry_run(self):
        """Test that send_live_message prints in dry-run mode."""
        with (
            patch("builtins.print") as mock_print,
            patch("lib.notify.should_send_comment_to_issue", return_value=True),
        ):
            send_live_message("123", "compiler-explorer/compiler-explorer", "fake_token", dry_run=True)

            print_calls = [call[0][0] for call in mock_print.call_args_list]
            self.assertIn("[DRY RUN] Would add 'live' label to compiler-explorer/compiler-explorer#123", print_calls)
            self.assertIn(
                "[DRY RUN] Would comment 'This is now live' on compiler-explorer/compiler-explorer#123", print_calls
            )

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
            patch("builtins.print") as mock_print,
        ):
            handle_notify("old_commit", "new_commit", "fake_token", dry_run=True)

            mock_send.assert_called_once_with(456, "compiler-explorer/compiler-explorer", "fake_token", dry_run=True)
            print_calls = [call[0][0] for call in mock_print.call_args_list]
            self.assertTrue(any("[DRY RUN] Would notify PR #456" in call for call in print_calls))

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

    def test_should_notify_issue_filters_external_repos(self):
        """Test that should_notify_issue filters out external repository issues."""
        from lib.notify import should_notify_issue

        # External repository issue (should be filtered out)
        external_edge = {
            "repository": {"owner": {"login": "sinonjs"}, "name": "samsam"},
            "number": 253,
            "labels": {"edges": []},
        }
        self.assertFalse(should_notify_issue(external_edge))

        # Compiler Explorer main repo (should be notified)
        ce_main_edge = {
            "repository": {"owner": {"login": "compiler-explorer"}, "name": "compiler-explorer"},
            "number": 123,
            "labels": {"edges": []},
        }
        self.assertTrue(should_notify_issue(ce_main_edge))

        # Compiler Explorer infra repo (should be notified)
        ce_infra_edge = {
            "repository": {"owner": {"login": "compiler-explorer"}, "name": "infra"},
            "number": 456,
            "labels": {"edges": []},
        }
        self.assertTrue(should_notify_issue(ce_infra_edge))

        # Issue with no number (should be filtered out)
        no_number_edge = {
            "repository": {"owner": {"login": "compiler-explorer"}, "name": "compiler-explorer"},
            "labels": {"edges": []},
        }
        self.assertFalse(should_notify_issue(no_number_edge))

        # Issue already marked as live (should be filtered out)
        live_edge = {
            "repository": {"owner": {"login": "compiler-explorer"}, "name": "compiler-explorer"},
            "number": 789,
            "labels": {"edges": [{"node": {"name": "live"}}]},
        }
        self.assertFalse(should_notify_issue(live_edge))

    def test_handle_notify_supports_cross_repo_issues(self):
        """Test that handle_notify can notify issues across CE repositories."""
        mock_commits = [{"sha": "abc123"}]
        mock_pr = {"number": 456, "labels": []}

        # Mock linked issues with both main repo and infra repo issues
        mock_linked_issues = {
            "data": {
                "repository": {
                    "pullRequest": {
                        "closingIssuesReferences": {
                            "edges": [
                                {
                                    "node": {
                                        "repository": {
                                            "owner": {"login": "compiler-explorer"},
                                            "name": "compiler-explorer",
                                        },
                                        "number": 123,
                                        "labels": {"edges": []},
                                    }
                                },
                                {
                                    "node": {
                                        "repository": {"owner": {"login": "compiler-explorer"}, "name": "infra"},
                                        "number": 456,
                                        "labels": {"edges": []},
                                    }
                                },
                                {
                                    "node": {
                                        "repository": {"owner": {"login": "sinonjs"}, "name": "samsam"},
                                        "number": 253,
                                        "labels": {"edges": []},
                                    }
                                },
                            ]
                        }
                    }
                }
            }
        }

        with (
            patch("lib.notify.list_inbetween_commits", return_value=mock_commits),
            patch("lib.notify.get_linked_pr", return_value=mock_pr),
            patch("lib.notify.send_live_message") as mock_send,
            patch("lib.notify.get_linked_issues", return_value=mock_linked_issues),
            patch("builtins.print") as mock_print,
        ):
            handle_notify("old_commit", "new_commit", "fake_token", dry_run=True)

            # Should be called 3 times: PR + 2 CE issues (external issue filtered out)
            self.assertEqual(mock_send.call_count, 3)

            # Check that PR notification happened
            mock_send.assert_any_call(456, "compiler-explorer/compiler-explorer", "fake_token", dry_run=True)

            # Check that CE main repo issue notification happened
            mock_send.assert_any_call(123, "compiler-explorer/compiler-explorer", "fake_token", dry_run=True)

            # Check that CE infra repo issue notification happened
            mock_send.assert_any_call(456, "compiler-explorer/infra", "fake_token", dry_run=True)

            # Verify external repo issue was NOT notified (sinonjs/samsam#253)
            for call_args in mock_send.call_args_list:
                self.assertNotIn("sinonjs", str(call_args))
                self.assertNotIn("samsam", str(call_args))

            # Check print output shows correct repo formatting
            print_calls = [call[0][0] for call in mock_print.call_args_list]
            self.assertTrue(any("compiler-explorer/compiler-explorer#123" in call for call in print_calls))
            self.assertTrue(any("compiler-explorer/infra#456" in call for call in print_calls))


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
