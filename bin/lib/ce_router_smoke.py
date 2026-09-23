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
from botocore.exceptions import ClientError

from lib.aws_utils import get_asg_info

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
    tracked: str | None = None
    """An open issue or PR this check is expected to fail against, until it ships."""


@dataclass
class Findings:
    results: list[CheckResult] = field(default_factory=list)

    def add(self, name: str, ok: bool, detail: str, seconds: float = 0.0, tracked: str | None = None) -> CheckResult:
        result = CheckResult(name=name, ok=ok, detail=detail, seconds=seconds, tracked=tracked)
        self.results.append(result)
        return result

    @property
    def failed(self) -> list[CheckResult]:
        """Failures that are not already accounted for by an open issue."""
        return [r for r in self.results if not r.ok and not r.tracked]

    @property
    def known(self) -> list[CheckResult]:
        """Checks failing against a tracked issue - expected, until that issue ships."""
        return [r for r in self.results if not r.ok and r.tracked]

    @property
    def unexpectedly_fixed(self) -> list[CheckResult]:
        """Tracked checks that pass here.

        Either the fix has landed, or this environment does not exercise the path - all
        three of these pass on a direct-routed environment, which makes such a run a useful
        control that the checks themselves are sound.
        """
        return [r for r in self.results if r.ok and r.tracked]


def in_service_worker_count(environment: str) -> int | None:
    """How many workers the environment has, or None if that could not be determined.

    Every check here compiles something, so with no workers each one waits out the router's
    60s deadline and the whole run looks like a broken router rather than an empty
    environment. Beta and staging idle at zero (min_instances is 0 for everything but
    prod), and their scale-from-zero is far slower than a request's lifetime, so this is
    the normal state between tests rather than an unusual one.
    """
    total = 0
    for colour in ("blue", "green"):
        try:
            info = get_asg_info(f"{environment}-{colour}")
        except ClientError as e:
            LOGGER.warning("Could not read the %s-%s ASG: %s", environment, colour, e)
            return None
        if info:
            total += sum(1 for i in info.get("Instances", []) if i.get("LifecycleState") == "InService")
    return total


def base_url(environment: str, override: str | None = None) -> str:
    """The API root for an environment. An override lets checks bypass CloudFront."""
    if override:
        return override.rstrip("/")
    if environment == "prod":
        return "https://godbolt.org"
    return f"https://godbolt.org/{environment}"


MARKER_DEFINE = "SMOKE_FLAG"
MARKER_SYMBOL = "smoke_marker_function"
EXEC_MARKER = "SMOKE_EXEC_OK"


def source_needing_a_define() -> str:
    """Source whose assembly only contains MARKER_SYMBOL when -D SMOKE_FLAG reached the compiler.

    A define is a cleaner probe than an optimisation level: the symbol is either in the
    output or it is not, with no dependence on what the compiler chose to do.
    """
    return f"#ifdef {MARKER_DEFINE}\nint {MARKER_SYMBOL}() {{ return 42; }}\n#endif\nint main() {{ return 0; }}\n"


def source_emitting_at_least(target_bytes: int) -> str:
    """C++ whose assembly output is at least roughly target_bytes.

    Each function contributes on the order of 120 bytes of asm at -O0, so this overshoots
    rather than undershoots; callers that care about a precise size check the response.
    """
    count = max(1, target_bytes // 120)
    body = "\n".join(f"int f{i}(int x) {{ return x * {i} + {i}; }}" for i in range(count))
    return body + "\nint main() { return 0; }\n"


def source_emitting_at_least_that_runs(target_bytes: int) -> str:
    """As above, but main prints EXEC_MARKER so execution output can be checked."""
    count = max(1, target_bytes // 120)
    body = "\n".join(f"int f{i}(int x) {{ return x * {i} + {i}; }}" for i in range(count))
    main = f'\nint main() {{ puts("{EXEC_MARKER}"); return 0; }}\n'
    return "#include <cstdio>\n" + body + main


def compile_body(source: str, user_arguments: str = "-O0", lang: str = "c++", **extra: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "source": source,
        "options": {
            "userArguments": user_arguments,
            "compilerOptions": {},
            "filters": {"labels": True, "directives": True, "commentOnly": True},
            "tools": [],
            "libraries": [],
        },
        "lang": lang,
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

# Compiler Explorer is 97 languages, not one. The router carries `lang` through to the worker,
# which looks a compiler up by (lang, compilerId), so each language is a distinct path rather
# than a cosmetic difference. These are the smallest valid program in each.
LANGUAGE_FIXTURES = {
    "c++": "int main() { return 0; }\n",
    "c": "int main(void) { return 0; }\n",
    "rust": "fn main() {}\n",
    "go": "package main\n\nfunc main() {}\n",
    "python": "print(1)\n",
}


@dataclass(frozen=True)
class BuildSystemFixture:
    """A minimal project for one build system: its manifest, its language, its sources."""

    lang: str
    source: str
    """The manifest - CMakeLists.txt, Cargo.toml, Makefile - which the API takes as `source`."""
    files: list[dict[str, str]]


# Sending a CMakeLists.txt to cargo tests nothing useful, so each build system gets its own.
BUILD_SYSTEM_FIXTURES: dict[str, BuildSystemFixture] = {
    "cmake": BuildSystemFixture(lang="c++", source=CMAKE_MANIFEST, files=CMAKE_FILES),
    "cargo": BuildSystemFixture(
        lang="rust",
        source='[package]\nname = "smoke"\nversion = "0.1.0"\nedition = "2021"\n',
        files=[{"filename": "src/main.rs", "contents": "fn main() {}\n"}],
    ),
    "make": BuildSystemFixture(lang="c++", source="all:\n\t$(CXX) -S example.cpp -o output.s\n", files=CMAKE_FILES),
}


def pick_compiler_for(base: str, lang: str, timeout: int = 30) -> str | None:
    """The compiler Compiler Explorer itself defaults to for a language.

    Asking the API beats a hardcoded list, which rots, and beats sorting ids, which lands on
    whatever is alphabetically last - zig for C++, tinygo for Go - so a failure would say more
    about an unusual toolchain than about the router.
    """
    try:
        response = requests.get(
            f"{base}/api/languages?fields=id,defaultCompiler",
            headers={"Accept": "application/json"},
            timeout=timeout,
        )
        response.raise_for_status()
        for entry in response.json():
            if entry.get("id") == lang and entry.get("defaultCompiler"):
                return str(entry["defaultCompiler"])
        LOGGER.warning("No default compiler advertised for %s", lang)
    except (requests.RequestException, ValueError, KeyError) as e:
        LOGGER.warning("Could not read the default compiler for %s: %s", lang, e)
    return None


def check_languages(base: str, findings: Findings) -> None:
    """One compile per language.

    Not require_success: a compiler may legitimately object to a minimal program, and what is
    under test is that the router delivered a well-formed result for that language. No user
    arguments either - -O0 is a C/C++ flag, and passing it to rustc turns this into a test of
    error delivery.
    """
    for lang, source in LANGUAGE_FIXTURES.items():
        compiler_id = pick_compiler_for(base, lang)
        if not compiler_id:
            findings.add(f"compile {lang}", False, "no default compiler advertised for this language")
            continue
        status, payload, secs = post_compile(
            _compile_url(base, compiler_id), compile_body(source, user_arguments="", lang=lang), timeout=120
        )
        ok, detail = classify_compilation(status, payload)
        findings.add(f"compile {lang} ({compiler_id})", ok, detail, secs)


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


def check_build_system(base: str, findings: Findings, build_system: str, suffix: str, label: str) -> None:
    """Build a project with the manifest, language and compiler that build system actually takes."""
    fixture = BUILD_SYSTEM_FIXTURES.get(build_system)
    if not fixture:
        findings.add(label, False, f"no fixture defined for build system '{build_system}'")
        return
    compiler_id = pick_compiler_for(base, fixture.lang)
    if not compiler_id:
        findings.add(label, False, f"no {fixture.lang} compiler available")
        return
    body = compile_body(fixture.source, user_arguments="", lang=fixture.lang, files=fixture.files)
    status, payload, secs = post_compile(_compile_url(base, compiler_id, suffix), body, timeout=180)
    ok, detail = classify_compilation(status, payload)
    findings.add(f"{label} [{fixture.lang}/{compiler_id}]", ok, detail, secs)


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
    check_languages(base, findings)
    check_build_system(base, findings, "cmake", "cmake", "cmake (legacy spelling)")
    for build_system in build_systems:
        check_build_system(base, findings, build_system, f"build/{build_system}", f"build/{build_system}")
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

    check_documented_text_api(base, queue_compiler, findings)
    check_accept_default(base, queue_compiler, findings)
    check_charset_keeps_user_arguments(base, queue_compiler, findings)
    check_oversized_execution_keeps_output(base, queue_compiler, findings)

    check_large_result(base, queue_compiler, findings)
    check_large_result_bypass_cache(base, queue_compiler, findings)
    check_large_result_project_build(base, queue_compiler, findings)

    if not skip_slow:
        check_large_request(base, queue_compiler, findings)
        check_result_size_sweep(base, queue_compiler, findings)
        check_large_response(base, queue_compiler, findings)

    return findings


def check_charset_keeps_user_arguments(base: str, compiler_id: str, findings: Findings) -> None:
    """A charset on the content-type must not cost the caller their compiler flags.

    Workers decide the request format with an exact string comparison against
    'application/json', so 'application/json; charset=utf-8' falls to the text path and
    userArguments, filters and libraries are dropped. The compile still succeeds, so the
    caller gets the right code built the wrong way with nothing logged anywhere.
    """
    body = compile_body(source_needing_a_define(), user_arguments=f"-D{MARKER_DEFINE}")
    status, payload, secs = post_compile(
        _compile_url(base, compiler_id), body, headers={"Content-Type": "application/json; charset=utf-8"}
    )
    ok, detail = classify_compilation(status, payload, require_success=True)
    if ok:
        reached = MARKER_SYMBOL in asm_text(payload)
        ok = reached
        detail = "-D reached the compiler" if reached else "compiled without the caller's -D: flags were dropped"
    findings.add("charset in content-type keeps user arguments", ok, detail, secs, tracked="compiler-explorer#9148")


def check_oversized_execution_keeps_output(base: str, compiler_id: str, findings: Findings) -> None:
    """An oversized result that also executed must still carry the program's output.

    Large results are handed over by reference, and the object is written before
    execResult is attached, so the reader is pointed at a body holding the asm and no
    program output. Only reachable through a path that fetches by s3Key, which means the
    router: served directly, the result never makes the round trip.
    """
    body = compile_body(source_emitting_at_least_that_runs(4 * WEBSOCKET_SIZE_THRESHOLD))
    body["options"]["filters"]["execute"] = True
    status, payload, secs = post_compile(_compile_url(base, compiler_id), body, timeout=180)
    ok, detail = classify_compilation(status, payload, require_success=True)
    if ok:
        exec_result = payload.get("execResult") or {}
        stdout = "\n".join(line.get("text", "") for line in (exec_result.get("stdout") or []))
        asm_size = len(asm_text(payload))
        if asm_size < WEBSOCKET_SIZE_THRESHOLD:
            ok, detail = False, f"asm only {asm_size}B - too small to be handed over by reference"
        elif EXEC_MARKER in stdout:
            detail = f"asm {asm_size // 1024}KB and the program's output survived"
        else:
            ok = False
            detail = (
                f"asm {asm_size // 1024}KB arrived but the program's output did not (execResult={exec_result!r:.80})"
            )
    findings.add("oversized result keeps execution output", ok, detail, secs, tracked="compiler-explorer#9149")


def check_documented_text_api(base: str, compiler_id: str, findings: Findings) -> None:
    """The documented text form: source as the body, options in the query string."""
    url = f"{_compile_url(base, compiler_id)}?options=-D{MARKER_DEFINE}"
    start = time.monotonic()
    response = requests.post(
        url,
        data=source_needing_a_define(),
        headers={"Content-Type": "text/plain", "Accept": "application/json"},
        timeout=90,
    )
    secs = time.monotonic() - start
    try:
        payload = response.json()
    except ValueError:
        findings.add("documented text/plain API", False, f"HTTP {response.status_code}, non-JSON body", secs)
        return
    ok, detail = classify_compilation(response.status_code, payload, require_success=True)
    if ok:
        reached = MARKER_SYMBOL in asm_text(payload)
        ok = reached
        detail = "query-string options reached the compiler" if reached else "?options= was dropped"
    findings.add("documented text/plain API", ok, detail, secs)


def check_accept_default(base: str, compiler_id: str, findings: Findings) -> None:
    """With no Accept header the documented default is plain text, not JSON."""
    start = time.monotonic()
    response = requests.post(
        _compile_url(base, compiler_id),
        data=json.dumps(compile_body("int main() { return 0; }")),
        headers={"Content-Type": "application/json"},
        timeout=90,
    )
    secs = time.monotonic() - start
    content_type = response.headers.get("content-type", "")
    is_text = content_type.startswith("text/plain")
    findings.add(
        "no Accept header returns the documented text default",
        is_text,
        f"content-type: {content_type or '(none)'}",
        secs,
        tracked="atlas F-16",
    )
