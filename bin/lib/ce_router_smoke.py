"""Functional smoke checks for a CE Router environment.

Covers section C of docs/ce-router-cutover-checklist.md: the request shapes that exercise
each distinct path through the router - queue routing, URL routing, the SQS overflow path
for oversized requests, and the s3Key path for oversized results.

The checks assert on what the user actually receives, not on status codes alone. Several
of the failures these are looking for return HTTP 200 with a broken body.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import requests

LOGGER = logging.getLogger(__name__)

# The router renders this when it has an s3Key but the object is not in the bucket.
S3_RESOLVE_FAILURE = "An internal error has occurred while retrieving the compilation result"

WEBSOCKET_SIZE_THRESHOLD = 31 * 1024
SQS_MAX_MESSAGE_SIZE = 262144


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str
    seconds: float = 0.0


@dataclass
class Findings:
    results: list[CheckResult] = field(default_factory=list)

    def add(self, name: str, ok: bool, detail: str, seconds: float = 0.0) -> CheckResult:
        result = CheckResult(name=name, ok=ok, detail=detail, seconds=seconds)
        self.results.append(result)
        return result

    @property
    def failed(self) -> list[CheckResult]:
        return [r for r in self.results if not r.ok]


def base_url(environment: str, override: str | None = None) -> str:
    """The API root for an environment. An override lets checks bypass CloudFront."""
    if override:
        return override.rstrip("/")
    if environment == "prod":
        return "https://godbolt.org"
    return f"https://godbolt.org/{environment}"


def source_emitting_at_least(target_bytes: int) -> str:
    """C++ whose assembly output is at least roughly target_bytes.

    Each function contributes on the order of 120 bytes of asm at -O0, so this overshoots
    rather than undershoots; callers that care about a precise size check the response.
    """
    count = max(1, target_bytes // 120)
    body = "\n".join(f"int f{i}(int x) {{ return x * {i} + {i}; }}" for i in range(count))
    return body + "\nint main() { return 0; }\n"


def compile_body(source: str, user_arguments: str = "-O0", **extra: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "source": source,
        "options": {
            "userArguments": user_arguments,
            "compilerOptions": {},
            "filters": {"labels": True, "directives": True, "commentOnly": True},
            "tools": [],
            "libraries": [],
        },
        "lang": "c++",
    }
    body.update(extra)
    return body


def asm_text(result: dict[str, Any]) -> str:
    return "\n".join(line.get("text", "") for line in result.get("asm") or [])


def stderr_text(result: dict[str, Any]) -> str:
    return "\n".join(line.get("text", "") for line in result.get("stderr") or [])


def post_compile(
    url: str, body: dict[str, Any], timeout: int = 90, headers: dict[str, str] | None = None
) -> tuple[int, Any, float]:
    """POST a compilation and return (status, parsed body or raw text, elapsed seconds)."""
    send_headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if headers:
        send_headers.update(headers)
    start = time.monotonic()
    response = requests.post(url, data=json.dumps(body), headers=send_headers, timeout=timeout)
    elapsed = time.monotonic() - start
    try:
        return response.status_code, response.json(), elapsed
    except ValueError:
        return response.status_code, response.text, elapsed


def cpp_compiler_ids(base: str, timeout: int = 30) -> set[str]:
    """Every C++ compiler id the environment reports.

    The routing table is language-agnostic, so picking from it alphabetically lands on
    things like `386_gl114` - an i386 Go compiler - which cannot build the generated C++ at
    all, and every size-dependent check then silently measures an empty result. Filtering
    candidates through this set keeps the checks honest.
    """
    try:
        response = requests.get(
            f"{base}/api/compilers/c++?fields=id", headers={"Accept": "application/json"}, timeout=timeout
        )
        response.raise_for_status()
        return {entry["id"] for entry in response.json()}
    except (requests.RequestException, ValueError, KeyError) as e:
        LOGGER.warning("Could not fetch the compiler list: %s", e)
        return set()


def pick_cpp_compiler(base: str, timeout: int = 30, candidates: set[str] | None = None) -> str | None:
    """A C++ compiler to drive the checks with, preferring a well-known stable id."""
    ids = candidates if candidates is not None else cpp_compiler_ids(base, timeout)
    for preferred in ("g132", "g142", "g122", "gsnapshot"):
        if preferred in ids:
            return preferred
    return sorted(ids)[0] if ids else None


def classify_compilation(status: int, payload: Any, require_success: bool = False) -> tuple[bool, str]:
    """Whether a compilation response is a usable result, and why not if it is not.

    A 200 is not enough: the s3Key path fails by returning a well-formed result whose
    stderr carries the router's internal-error text, and a result with no asm and no
    diagnostics is equally useless to the caller.
    """
    if status != 200:
        detail = payload if isinstance(payload, str) else json.dumps(payload)[:200]
        return False, f"HTTP {status}: {detail[:200]}"
    if not isinstance(payload, dict):
        return False, f"non-object body: {str(payload)[:120]}"
    if S3_RESOLVE_FAILURE in stderr_text(payload):
        return False, "router could not resolve s3Key - result object missing from the bucket"
    if payload.get("code") is None:
        return False, f"no exit code in result: {json.dumps(payload)[:160]}"
    detail = f"code={payload['code']} asm={len(asm_text(payload))}B"
    if require_success and payload["code"] != 0:
        # The check measures the response, so a compiler error means it measured nothing.
        return False, f"compilation failed ({detail}) - check did not exercise its path: {stderr_text(payload)[:120]}"
    return True, detail


CMAKE_MANIFEST = "cmake_minimum_required(VERSION 3.10)\nproject(smoke CXX)\nadd_executable(smoke example.cpp)\n"
CMAKE_FILES = [{"filename": "example.cpp", "contents": "int main() { return 0; }\n"}]


def _compile_url(base: str, compiler_id: str, suffix: str = "compile") -> str:
    return f"{base}/api/compiler/{compiler_id}/{suffix}"


def check_plain_compile(base: str, compiler_id: str, findings: Findings) -> None:
    status, payload, secs = post_compile(_compile_url(base, compiler_id), compile_body("int main() { return 0; }"))
    ok, detail = classify_compilation(status, payload)
    findings.add("plain compile", ok, detail, secs)


def check_cache_hit_loop(base: str, compiler_id: str, findings: Findings, iterations: int = 50) -> None:
    """The same request repeatedly. A cache hit returns in milliseconds, which is the
    tightest window for the subscribe/result race (atlas S9.2)."""
    body = compile_body("int main() { return 41 + 1; }", user_arguments="-O1")
    url = _compile_url(base, compiler_id)
    failures, times = [], []
    for i in range(iterations):
        status, payload, secs = post_compile(url, body)
        times.append(secs)
        ok, detail = classify_compilation(status, payload)
        if not ok:
            failures.append(f"#{i}: {detail}")
    slowest = max(times) if times else 0.0
    detail = f"{iterations - len(failures)}/{iterations} ok, slowest {slowest:.2f}s"
    if failures:
        detail += f" | first failure {failures[0]}"
    findings.add(f"cache-hit loop x{iterations}", not failures, detail, sum(times))


def check_execute(base: str, compiler_id: str, findings: Findings) -> None:
    body = compile_body('#include <cstdio>\nint main() { puts("smoke"); return 0; }')
    body["options"]["filters"]["execute"] = True
    status, payload, secs = post_compile(_compile_url(base, compiler_id), body)
    ok, detail = classify_compilation(status, payload)
    if ok and not (payload.get("execResult") or payload.get("didExecute")):
        ok, detail = False, "compiled but no execResult - the execution path did not run"
    findings.add("compile with execution", ok, detail, secs)


def check_build_system(base: str, compiler_id: str, findings: Findings, suffix: str, label: str) -> None:
    body = compile_body(CMAKE_MANIFEST, files=CMAKE_FILES)
    status, payload, secs = post_compile(_compile_url(base, compiler_id, suffix), body, timeout=120)
    ok, detail = classify_compilation(status, payload)
    findings.add(label, ok, detail, secs)


def check_unknown_build_system(base: str, compiler_id: str, findings: Findings) -> None:
    """An unknown build system must surface as a failed compilation naming it, not a 500:
    a producer can be ahead of a worker across a deploy."""
    body = compile_body(CMAKE_MANIFEST, files=CMAKE_FILES)
    status, payload, secs = post_compile(_compile_url(base, compiler_id, "build/definitelynotabuildsystem"), body)
    blob = json.dumps(payload) if not isinstance(payload, str) else payload
    names_it = "definitelynotabuildsystem" in blob
    # The two paths answer differently and both are acceptable: the HTTP route rejects it
    # with a 404 naming it, while via the router the worker throws and it comes back as a
    # failed compilation. What matters is that it is refused and the name is echoed, rather
    # than being silently read as "no build system" and compiled as a plain source file.
    if status == 404 and names_it:
        findings.add("unknown build system", True, "404 naming it (direct HTTP path)", secs)
    elif status == 200 and names_it:
        findings.add("unknown build system", True, "compilation error naming it (router path)", secs)
    else:
        findings.add("unknown build system", False, f"HTTP {status}, body: {blob[:160]}", secs)


def check_large_request(base: str, compiler_id: str, findings: Findings) -> None:
    """Over the SQS limit, so the request goes via the S3 overflow path."""
    source = source_emitting_at_least(8 * 1024) + "// " + ("x" * SQS_MAX_MESSAGE_SIZE) + "\n"
    body = compile_body(source)
    sent = len(json.dumps(body))
    status, payload, secs = post_compile(_compile_url(base, compiler_id), body, timeout=120)
    ok, detail = classify_compilation(status, payload)
    findings.add(f"large request ({sent // 1024}KB, S3 overflow)", ok, detail, secs)


def check_large_result(base: str, compiler_id: str, findings: Findings) -> None:
    """Over the websocket threshold, so the result comes back by s3Key reference."""
    body = compile_body(source_emitting_at_least(4 * WEBSOCKET_SIZE_THRESHOLD))
    status, payload, secs = post_compile(_compile_url(base, compiler_id), body, timeout=120)
    ok, detail = classify_compilation(status, payload, require_success=True)
    if ok and len(asm_text(payload)) < WEBSOCKET_SIZE_THRESHOLD:
        ok, detail = False, f"asm only {len(asm_text(payload))}B - did not exercise the s3Key path"
    findings.add("large result (s3Key path)", ok, detail, secs)


def check_large_result_bypass_cache(base: str, compiler_id: str, findings: Findings) -> None:
    """Not cacheable, so the worker stores it under cache/temp/ instead. A different
    branch of the same path, and one that has produced missing objects before."""
    body = compile_body(source_emitting_at_least(4 * WEBSOCKET_SIZE_THRESHOLD), user_arguments="-O0 -g")
    body["bypassCache"] = 1
    status, payload, secs = post_compile(_compile_url(base, compiler_id), body, timeout=120)
    ok, detail = classify_compilation(status, payload, require_success=True)
    findings.add("large result + bypassCache", ok, detail, secs)


def check_large_result_project_build(base: str, compiler_id: str, findings: Findings) -> None:
    """The delayCaching branch: the inner result is assigned an s3Key without being stored."""
    files = [{"filename": "example.cpp", "contents": source_emitting_at_least(4 * WEBSOCKET_SIZE_THRESHOLD)}]
    body = compile_body(CMAKE_MANIFEST, files=files)
    status, payload, secs = post_compile(_compile_url(base, compiler_id, "cmake"), body, timeout=180)
    ok, detail = classify_compilation(status, payload)
    findings.add("large result from project build", ok, detail, secs)


def check_result_size_sweep(base: str, compiler_id: str, findings: Findings) -> None:
    """Sizes bracketing the 31KiB threshold. The worker and the compiler measure slightly
    different values, so results near the boundary can be sent by reference without having
    been stored."""
    url = _compile_url(base, compiler_id)
    failures = []
    for fraction in (0.9, 0.98, 1.0, 1.02, 1.1):
        target = int(WEBSOCKET_SIZE_THRESHOLD * fraction)
        status, payload, _ = post_compile(url, compile_body(source_emitting_at_least(target)), timeout=120)
        ok, detail = classify_compilation(status, payload, require_success=True)
        if not ok:
            failures.append(f"{fraction:g}x: {detail}")
    findings.add(
        "31KiB boundary sweep",
        not failures,
        "all sizes returned a usable result" if not failures else " | ".join(failures),
    )


def check_large_response(base: str, compiler_id: str, findings: Findings) -> None:
    body = compile_body(source_emitting_at_least(1_200_000))
    status, payload, secs = post_compile(_compile_url(base, compiler_id), body, timeout=180)
    ok, detail = classify_compilation(status, payload, require_success=True)
    if ok:
        detail += f" (response asm {len(asm_text(payload)) // 1024}KB)"
    findings.add("response over 1MB", ok, detail, secs)


def run_checks(
    base: str,
    queue_compiler: str,
    url_compiler: str | None = None,
    unrouted_compiler: str | None = None,
    build_systems: tuple[str, ...] = ("cmake",),
    loop_iterations: int = 50,
    skip_slow: bool = False,
) -> Findings:
    """Run checklist section C. Returns findings; the caller decides how to report."""
    findings = Findings()

    check_plain_compile(base, queue_compiler, findings)
    check_cache_hit_loop(base, queue_compiler, findings, loop_iterations)
    check_execute(base, queue_compiler, findings)
    check_build_system(base, queue_compiler, findings, "cmake", "cmake (legacy spelling)")
    for build_system in build_systems:
        check_build_system(base, queue_compiler, findings, f"build/{build_system}", f"build/{build_system}")
    check_unknown_build_system(base, queue_compiler, findings)

    if url_compiler:
        status, payload, secs = post_compile(
            _compile_url(base, url_compiler), compile_body("int main() { return 0; }"), timeout=120
        )
        ok, detail = classify_compilation(status, payload)
        findings.add(f"URL-routed compiler ({url_compiler})", ok, detail, secs)

    if unrouted_compiler:
        status, payload, secs = post_compile(
            _compile_url(base, unrouted_compiler), compile_body("int main() { return 0; }"), timeout=120
        )
        ok, detail = classify_compilation(status, payload)
        findings.add(f"compiler absent from routing table ({unrouted_compiler})", ok, detail, secs)

    check_large_result(base, queue_compiler, findings)
    check_large_result_bypass_cache(base, queue_compiler, findings)
    check_large_result_project_build(base, queue_compiler, findings)

    if not skip_slow:
        check_large_request(base, queue_compiler, findings)
        check_result_size_sweep(base, queue_compiler, findings)
        check_large_response(base, queue_compiler, findings)

    return findings
