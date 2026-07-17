"""Tests for source-map handling in the CDN deployment job."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from lib.cdn import DeploymentJob, is_source_map


class TestIsSourceMap(unittest.TestCase):
    def test_matches_maps(self):
        assert is_source_map("noscript.v69.abcdef.js.map")
        assert is_source_map("noscript.v69.abcdef.css.map")

    def test_rejects_code(self):
        assert not is_source_map("noscript.v69.abcdef.js")
        assert not is_source_map("noscript.v69.abcdef.css")
        assert not is_source_map("image.map.png")


class TestUploadCacheControl(unittest.TestCase):
    def _upload_and_capture(self, name):
        cc = "public, max-age=31536000"
        job = DeploymentJob("dummy.tar", "bucket", cache_control=cc)
        with patch("lib.cdn.s3_client") as mock_s3:
            job._upload_file({"name": name, "hash": "deadbeef", "path": Path("/tmp/x")})
        # ExtraArgs is the keyword passed to s3_client.upload_file
        _, kwargs = mock_s3.upload_file.call_args
        return kwargs["ExtraArgs"]["CacheControl"]

    def test_map_is_uncached(self):
        assert self._upload_and_capture("noscript.v69.abcdef.js.map") == "no-cache"

    def test_code_keeps_immutable_policy(self):
        assert self._upload_and_capture("noscript.v69.abcdef.js") == "public, max-age=31536000"


class TestRunMapMismatch(unittest.TestCase):
    """A map mismatch must overwrite (upload) rather than abort the deploy,
    while a genuine code mismatch must still abort."""

    def _run_with(self, mismatch_name):
        job = DeploymentJob("dummy.tar", "bucket")
        files = [
            {"name": "app.ABC.js", "path": Path("/tmp/js")},
            {"name": "app.ABC.js.map", "path": Path("/tmp/map")},
        ]

        def fake_check(f):
            return {**f, "exists": True, "mismatch": f["name"] == mismatch_name, "s3hash": "old"}

        with (
            patch.object(DeploymentJob, "_DeploymentJob__unpack_tar", return_value=files),
            patch("lib.cdn.hash_file_for_s3", side_effect=lambda f: {**f, "hash": "new"}),
            patch.object(job, "_check_s3_hash", side_effect=fake_check),
            patch.object(job, "_upload_file", side_effect=lambda f: f) as mock_upload,
            patch.object(job, "_update_tags", side_effect=lambda f: f),
        ):
            result = job.run()
        uploaded = {c.args[0]["name"] for c in mock_upload.call_args_list}
        return result, uploaded

    def test_map_mismatch_overwrites_and_succeeds(self):
        result, uploaded = self._run_with("app.ABC.js.map")
        assert result is True
        assert "app.ABC.js.map" in uploaded

    def test_code_mismatch_still_aborts(self):
        result, uploaded = self._run_with("app.ABC.js")
        assert result is False


class TestCheckHashesMapExempt(unittest.TestCase):
    def _check_with(self, mismatch_name):
        job = DeploymentJob("dummy.tar", "bucket")
        files = [
            {"name": "app.ABC.js", "path": Path("/tmp/js")},
            {"name": "app.ABC.js.map", "path": Path("/tmp/map")},
        ]

        def fake_check(f):
            return {**f, "exists": True, "mismatch": f["name"] == mismatch_name, "s3hash": "old"}

        with (
            patch.object(DeploymentJob, "_DeploymentJob__unpack_tar", return_value=files),
            patch("lib.cdn.hash_file_for_s3", side_effect=lambda f: {**f, "hash": "new"}),
            patch.object(job, "_check_s3_hash", side_effect=fake_check),
        ):
            return job.check_hashes()

    def test_map_mismatch_passes(self):
        assert self._check_with("app.ABC.js.map") is True

    def test_code_mismatch_fails(self):
        assert self._check_with("app.ABC.js") is False


if __name__ == "__main__":
    unittest.main()
