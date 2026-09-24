"""Ramped load against a CE environment, for the section G items of the cutover checklist.

The rate climbs continuously rather than in steps, because what is under test is how the
queue-depth scaling policy responds, and it needs minutes of sustained backlog before it acts.
A step change tells you less about that than a ramp does.

Requests are issued with asyncio rather than a thread pool. That is not a style preference: a
pool of N threads can only ever have N requests outstanding, so once latency rises the offered
rate silently becomes `N / latency` instead of what was asked for, and the run measures a
closed-loop equilibrium while appearing to measure capacity. A run at 25 req/s against a 90s
timeout needs room for a couple of thousand requests in flight, which is nothing for asyncio.
The cap that does exist is reported whenever it binds, so the numbers are never quietly wrong.

Two things make an unattended load test here risky, and both are handled rather than hoped
about:

- `events-connections` is shared with prod, so load aimed at beta can reach prod through it.
  That has happened. Every reporting window checks the table's throttle alarms and stops the
  run if either leaves OK, instead of finding out afterwards in the metrics.
- Requests keep costing capacity after the generator stops, because each one's unsubscribe
  lands about a minute later. The run watches a tail period rather than exiting at the peak.
"""

from __future__ import annotations

import asyncio
import random
import statistics
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass

import aiohttp
import boto3

THROTTLE_ALARMS = ["EventsConnectionsWriteThrottled", "EventsConnectionsIndexWriteThrottled"]
REQUEST_TIMEOUT_SECONDS = 90

# Say plainly what this is. The client library's own default gets caught by the WAF's
# rate-limit-non-browser rule, which allows 100 requests a minute - below the capacity of a
# single worker, so a load test cannot generate load at all. A recognisable agent is also a
# better thing to write an exception against than a source address, which changes.
USER_AGENT = "ce-router-load/1.0 (+https://github.com/compiler-explorer/infra) Compiler Explorer load test"


@dataclass(frozen=True)
class Payload:
    name: str
    weight: int
    build: Callable[[str, int], str]
    #: Whether the compiler is expected to exit zero. A failing compile is an ordinary thing for
    #: this API to carry, and it travels differently: the text is in stderr rather than asm.
    expect_success: bool


def _small(marker: str, n: int) -> str:
    return f"int {marker}() {{ return {n}; }}\n"


def _medium(marker: str, n: int) -> str:
    return (
        "#include <vector>\n#include <algorithm>\n#include <string>\n#include <map>\n"
        f"int {marker}(std::map<std::string, std::vector<int>>& in) {{\n"
        "  int t = 0;\n"
        "  for (auto& [k, v] : in) { std::sort(v.begin(), v.end()); t += v.size() + k.size(); }\n"
        f"  return t + {n};\n}}\n"
    )


def _large(marker: str, n: int) -> str:
    return f"int {marker}() {{ return {n}; }}\n" + "".join(
        f"int {marker}_f{i}(int x) {{ return x * {i} + {n}; }}\n" for i in range(600)
    )


def _failing(marker: str, n: int) -> str:
    return f"int {marker}() {{ return undeclared_value_{n}; }}\n"


def _failing_large(marker: str, n: int) -> str:
    # About 140KB of diagnostics, so the result crosses the 31KiB threshold and travels by
    # s3Key carrying stderr rather than asm - a shape nothing else here produces.
    return "".join(f"int {marker}_e{i}() {{ return undeclared_{i}_{n}; }}\n" for i in range(400))


# Real traffic is mostly small snippets, with a tail of heavy ones and a healthy share that do
# not compile at all, since people iterate on broken code.
PAYLOADS = [
    Payload("small", 65, _small, expect_success=True),
    Payload("medium", 12, _medium, expect_success=True),
    Payload("large", 5, _large, expect_success=True),
    Payload("failing", 13, _failing, expect_success=False),
    Payload("failing-large", 5, _failing_large, expect_success=False),
]
_WEIGHTED = [p for p in PAYLOADS for _ in range(p.weight)]


def weighted_mix(only: str | None) -> list[Payload]:
    """The payload mix to draw from, optionally restricted to one class.

    Restricting to a slow class is how a single worker can be overloaded from one machine at
    all: the WAF allows 100 requests a minute, and a worker gets through more small compiles
    than that, so the only way to build a backlog inside the limit is to make each request
    cost more.
    """
    if only is None:
        return _WEIGHTED
    chosen = [p for p in PAYLOADS if p.name == only]
    if not chosen:
        raise ValueError(f"unknown payload class {only!r}; have {', '.join(p.name for p in PAYLOADS)}")
    return chosen


def _text_of(payload: dict, key: str) -> str:
    return "\n".join(line.get("text", "") for line in payload.get(key, []) or [])


class Ramp:
    def __init__(self, base: str, compiler: str, asg_name: str, only: str | None = None):
        self.base, self.compiler, self.asg_name = base, compiler, asg_name
        self.mix = weighted_mix(only)
        self.cw = boto3.client("cloudwatch")
        self.asg = boto3.client("autoscaling")
        self.run_id = uuid.uuid4().hex[:6]
        self.counter = 0
        self.in_flight = 0
        self.peak_in_flight = 0
        self.refused = 0
        self.outcomes: list[tuple[str, float, str]] = []

    def alarm_states(self) -> dict[str, str]:
        alarms = self.cw.describe_alarms(AlarmNames=THROTTLE_ALARMS)["MetricAlarms"]
        return {a["AlarmName"]: a["StateValue"] for a in alarms}

    def capacity(self) -> tuple[int, int]:
        group = self.asg.describe_auto_scaling_groups(AutoScalingGroupNames=[self.asg_name])["AutoScalingGroups"][0]
        return group["DesiredCapacity"], sum(1 for i in group["Instances"] if i["LifecycleState"] == "InService")

    async def one(self, session: aiohttp.ClientSession) -> None:
        self.counter += 1
        n = self.counter
        payload = random.choice(self.mix)
        marker = f"load_{self.run_id}_{n}"
        self.in_flight += 1
        self.peak_in_flight = max(self.peak_in_flight, self.in_flight)
        started = time.time()
        try:
            async with session.post(
                f"{self.base}/api/compiler/{self.compiler}/compile",
                json={
                    "source": payload.build(marker, n),
                    "options": {
                        "userArguments": "",
                        "filters": {
                            "labels": True,
                            "directives": True,
                            "commentOnly": True,
                            "intel": True,
                            "demangle": True,
                        },
                    },
                    "lang": "c++",
                },
                headers={"Accept": "application/json", "User-Agent": USER_AGENT},
            ) as response:
                secs = time.time() - started
                if response.status != 200:
                    self.outcomes.append((f"http_{response.status}", secs, payload.name))
                    return
                body = await response.json()
                self.outcomes.append((self._classify(body, marker, payload), secs, payload.name))
        except TimeoutError:
            self.outcomes.append(("timeout", time.time() - started, payload.name))
        except aiohttp.ClientError as e:
            self.outcomes.append((f"error_{type(e).__name__}", time.time() - started, payload.name))
        finally:
            self.in_flight -= 1

    def _classify(self, body: dict, marker: str, payload: Payload) -> str:
        code = body.get("code")
        if code is None:
            return "no_exit_code"
        if payload.expect_success:
            if code != 0:
                return "unexpected_failure"
            # Its own marker, not just any result: under load is exactly when a result could
            # come back to the wrong caller, and that would otherwise look like a success.
            return "ok" if marker in _text_of(body, "asm") else "wrong_result"
        if code == 0:
            return "unexpected_success"
        # A failed compile has to arrive as the compiler's own words. The router fabricates a
        # well-formed result with its own text in stderr when it cannot resolve an s3Key, and
        # only the marker distinguishes that from a real diagnostic.
        return "ok" if marker in _text_of(body, "stderr") else "wrong_error"


def _report(ramp: Ramp, elapsed: int, rate: float, capacity: tuple[int, int], cap: int) -> None:
    done = ramp.outcomes
    ramp.outcomes = []
    if not done:
        print(f"t+{elapsed:4d}s rate={rate:4.1f}/s  (nothing completed in this window)", flush=True)
        return
    counts: dict[str, int] = {}
    by_class: dict[str, list[int]] = {}
    for kind, _, name in done:
        counts[kind] = counts.get(kind, 0) + 1
        slot = by_class.setdefault(name, [0, 0])
        slot[0] += 1
        slot[1] += kind == "ok"
    latencies = sorted(secs for _, secs, _ in done)
    ok = counts.get("ok", 0)
    desired, in_service = capacity
    failures = {k: v for k, v in counts.items() if k != "ok"}
    saturated = " SATURATED" if ramp.peak_in_flight >= cap else ""
    print(
        f"t+{elapsed:4d}s rate={rate:4.1f}/s done={len(done):4d} ok={100 * ok // len(done):3d}% "
        f"p50={statistics.median(latencies):5.1f}s p95={latencies[int(len(latencies) * 0.95)]:5.1f}s "
        f"| workers {in_service}/{desired} | inflight {ramp.in_flight}/{cap}{saturated} | "
        + " ".join(f"{c}:{v[1]}/{v[0]}" for c, v in sorted(by_class.items()))
        + (f" | {failures}" if failures else ""),
        flush=True,
    )
    ramp.peak_in_flight = ramp.in_flight


async def _drive(
    ramp: Ramp,
    rate_start: float,
    rate_end: float,
    ramp_seconds: int,
    window: int,
    tail_windows: int,
) -> bool:
    # Room for everything that can be outstanding at the top of the ramp for a whole timeout,
    # so the pool is not what limits the offered rate. It is reported if it ever binds.
    cap = max(64, int(rate_end * (REQUEST_TIMEOUT_SECONDS + 30)))
    connector = aiohttp.TCPConnector(limit=cap, limit_per_host=cap, ttl_dns_cache=300)
    timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)

    def rate_at(elapsed: float) -> float:
        return rate_start + (rate_end - rate_start) * min(1.0, elapsed / ramp_seconds)

    aborted = None
    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        started = time.time()
        tasks: set[asyncio.Task] = set()
        next_send = started
        next_report = started + window
        while time.time() - started < ramp_seconds and not aborted:
            now = time.time()
            if now >= next_send:
                if ramp.in_flight < cap:
                    task = asyncio.create_task(ramp.one(session))
                    tasks.add(task)
                    task.add_done_callback(tasks.discard)
                else:
                    ramp.refused += 1
                next_send += 1.0 / rate_at(now - started)
                continue
            if now >= next_report:
                capacity = await asyncio.to_thread(ramp.capacity)
                _report(ramp, int(now - started), rate_at(now - started), capacity, cap)
                states = await asyncio.to_thread(ramp.alarm_states)
                if any(state != "OK" for state in states.values()):
                    aborted = f"the shared events table is throttling: {states}"
                next_report += window
                continue
            await asyncio.sleep(min(0.02, max(0.0, min(next_send, next_report) - now)))

        if aborted:
            print(f"\nABORTED: {aborted}", flush=True)
        print(f"Draining {len(tasks)} in-flight request(s)...", flush=True)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        capacity = await asyncio.to_thread(ramp.capacity)
        _report(ramp, int(time.time() - started), rate_at(time.time() - started), capacity, cap)

    if ramp.refused:
        print(
            f"NOTE: {ramp.refused} request(s) were never sent because {cap} were already in flight. "
            "The offered rate was below the requested rate for part of this run.",
            flush=True,
        )
    print("=== tail: each request's unsubscribe lands about a minute later ===", flush=True)
    for i in range(tail_windows):
        await asyncio.sleep(30)
        states = await asyncio.to_thread(ramp.alarm_states)
        capacity = await asyncio.to_thread(ramp.capacity)
        print(f"  +{(i + 1) * 30}s alarms={states} workers={capacity}", flush=True)
    return aborted is None


def run_ramp(
    base: str,
    compiler: str,
    asg_name: str,
    rate_start: float,
    rate_end: float,
    ramp_seconds: int,
    window: int = 60,
    tail_windows: int = 6,
    only: str | None = None,
) -> bool:
    """Ramp from rate_start to rate_end, returning True if it finished without aborting."""
    ramp = Ramp(base, compiler, asg_name, only)
    mix = only if only else ", ".join(f"{p.name} {p.weight}%" for p in PAYLOADS)
    print(f"Run {ramp.run_id}: ramping {rate_start:g} -> {rate_end:g} req/s over {ramp_seconds}s against {base}")
    print(f"Mix: {mix}")
    print(f"Start: alarms={ramp.alarm_states()} workers={ramp.capacity()}", flush=True)
    return asyncio.run(_drive(ramp, rate_start, rate_end, ramp_seconds, window, tail_windows))
