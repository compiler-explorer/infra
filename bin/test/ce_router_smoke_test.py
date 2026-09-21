from __future__ import annotations

import json

from lib.ce_router_smoke import (  # noqa: I001
    S3_RESOLVE_FAILURE,
    WEBSOCKET_SIZE_THRESHOLD,
    Findings,
    asm_text,
    base_url,
    classify_compilation,
    compile_body,
    source_emitting_at_least,
)


class TestBaseUrl:
    def test_prod_has_no_env_prefix(self):
        assert base_url("prod") == "https://godbolt.org"

    def test_other_environments_are_prefixed(self):
        assert base_url("beta") == "https://godbolt.org/beta"

    def test_override_wins_and_loses_its_trailing_slash(self):
        assert base_url("beta", "https://alb.godbolt.org/") == "https://alb.godbolt.org"


class TestSourceGeneration:
    def test_larger_targets_produce_more_source(self):
        small = source_emitting_at_least(WEBSOCKET_SIZE_THRESHOLD)
        large = source_emitting_at_least(4 * WEBSOCKET_SIZE_THRESHOLD)
        assert len(large) > len(small)

    def test_always_compilable(self):
        for target in (0, 1, 1024, WEBSOCKET_SIZE_THRESHOLD):
            assert source_emitting_at_least(target).endswith("int main() { return 0; }\n")


class TestCompileBody:
    def test_carries_the_fields_the_json_api_requires(self):
        body = compile_body("int main(){}")
        assert body["source"] == "int main(){}"
        assert body["options"]["userArguments"] == "-O0"

    def test_extra_fields_are_merged(self):
        body = compile_body("x", files=[{"filename": "a.cpp", "contents": "y"}])
        assert body["files"][0]["filename"] == "a.cpp"


class TestClassifyCompilation:
    def test_a_normal_result_passes(self):
        ok, detail = classify_compilation(200, {"code": 0, "asm": [{"text": "main:"}]})
        assert ok
        assert "code=0" in detail

    def test_a_failed_compilation_is_still_a_usable_result(self):
        # A compiler error is a legitimate answer; the router delivered it.
        ok, _ = classify_compilation(200, {"code": 1, "stderr": [{"text": "error: ..."}], "asm": []})
        assert ok

    def test_non_200_fails(self):
        ok, detail = classify_compilation(408, {"error": "Compilation timeout"})
        assert not ok
        assert "408" in detail

    def test_the_routers_s3_failure_text_fails_despite_http_200(self):
        # The case this whole check exists for: a well-formed 200 carrying an internal error.
        ok, detail = classify_compilation(200, {"code": -1, "stderr": [{"text": S3_RESOLVE_FAILURE}]})
        assert not ok
        assert "s3Key" in detail

    def test_a_result_with_no_exit_code_fails(self):
        ok, _ = classify_compilation(200, {"okToCache": False})
        assert not ok

    def test_a_non_object_body_fails(self):
        ok, _ = classify_compilation(200, "# Compilation provided by Compiler Explorer")
        assert not ok


class TestFindings:
    def test_failed_collects_only_failures(self):
        findings = Findings()
        findings.add("a", True, "fine")
        findings.add("b", False, "broken")
        assert [r.name for r in findings.failed] == ["b"]


class TestAsmText:
    def test_joins_lines(self):
        assert asm_text({"asm": [{"text": "a"}, {"text": "b"}]}) == "a\nb"

    def test_tolerates_missing_asm(self):
        assert asm_text({}) == ""
        assert asm_text({"asm": None}) == ""
