"""Ramped load against a CE environment, for the section G items of the cutover checklist.

The rate climbs continuously rather than in steps, because what is under test is how the
queue-depth scaling policy responds, and it needs minutes of sustained backlog before it acts.
A step change tells you less about that than a ramp does.

Two things make an unattended load test here risky, and both are handled rather than hoped
about:

- `events-connections` is shared with prod, so load aimed at beta can reach prod through it.
  That has happened. Every reporting window checks the table's throttle alarms and stops the
  run if either leaves OK, instead of finding out afterwards in the metrics.
- Requests keep costing capacity after the generator stops, because each one's unsubscribe
  lands about a minute later. The run watches a tail period rather than exiting at the peak.
"""

from __future__ import annotations

import random
import statistics
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor

import boto3
import requests

THROTTLE_ALARMS = ["EventsConnectionsWriteThrottled", "EventsConnectionsIndexWriteThrottled"]

# Real traffic is mostly trivial snippets with a tail of heavy ones. The medium and large
# classes both exceed the 31KiB websocket threshold, so a fifth of the load travels by s3Key -
# the path that fails by returning a well-formed result carrying the router's error text, and
# the one most likely to misbehave when everything else is slow.
PAYLOADS = [
    ("small", 80, lambda marker, n: f"int {marker}() {{ return {n}; }}\n"),
    (
        "medium",
        15,
        lambda marker, n: (
            "#include <vector>\n#include <algorithm>\n#include <string>\n#include <map>\n"
            f"int {marker}(std::map<std::string, std::vector<int>>& in) {{\n"
            "  int t = 0;\n"
            "  for (auto& [k, v] : in) { std::sort(v.begin(), v.end()); t += v.size() + k.size(); }\n"
            f"  return t + {n};\n}}\n"
        ),
    ),
    (
        "large",
        5,
        lambda marker, n: (
            f"int {marker}() {{ return {n}; }}\n"
            + "".join(f"int {marker}_f{i}(int x) {{ return x * {i} + {n}; }}\n" for i in range(600))
        ),
    ),
]
_WEIGHTED = [name for name, weight, _ in PAYLOADS for _ in range(weight)]
_BUILDERS = {name: fn for name, _, fn in PAYLOADS}


class Ramp:
    def __init__(self, base: str, compiler: str, asg_name: str):
        self.base, self.compiler, self.asg_name = base, compiler, asg_name
        self.cw = boto3.client("cloudwatch")
        self.asg = boto3.client("autoscaling")
        self.session = requests.Session()
        self.session.mount("https://", requests.adapters.HTTPAdapter(pool_maxsize=256))
        self.run_id = uuid.uuid4().hex[:6]
        self._counter = iter(range(10**9))
        self._lock = threading.Lock()

    def _next(self) -> int:
        with self._lock:
            return next(self._counter)

    def alarm_states(self) -> dict[str, str]:
        alarms = self.cw.describe_alarms(AlarmNames=THROTTLE_ALARMS)["MetricAlarms"]
        return {a["AlarmName"]: a["StateValue"] for a in alarms}

    def capacity(self) -> tuple[int, int]:
        group = self.asg.describe_auto_scaling_groups(AutoScalingGroupNames=[self.asg_name])["AutoScalingGroups"][0]
        return group["DesiredCapacity"], sum(1 for i in group["Instances"] if i["LifecycleState"] == "InService")

    def one(self) -> tuple[str, float, str]:
        n = self._next()
        marker = f"load_{self.run_id}_{n}"
        payload_class = random.choice(_WEIGHTED)
        started = time.time()
        try:
            response = self.session.post(
                f"{self.base}/api/compiler/{self.compiler}/compile",
                json={
                    "source": _BUILDERS[payload_class](marker, n),
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
                headers={"Accept": "application/json"},
                timeout=90,
            )
            secs = time.time() - started
            if response.status_code != 200:
                return (f"http_{response.status_code}", secs, payload_class)
            result = response.json()
            if result.get("code") != 0:
                return ("compile_fail", secs, payload_class)
            asm = "\n".join(line.get("text", "") for line in result.get("asm", []))
            # Its own marker, not just any result: under load is exactly when a result could
            # come back to the wrong caller, and that would otherwise look like a success.
            return ("ok" if marker in asm else "wrong_result", secs, payload_class)
        except requests.Timeout:
            return ("timeout", time.time() - started, payload_class)
        except requests.RequestException as e:
            return (f"error_{type(e).__name__}", time.time() - started, payload_class)


def _report(elapsed: int, rate: float, done: list[tuple[str, float, str]], capacity: tuple[int, int]) -> None:
    counts: dict[str, int] = {}
    by_class: dict[str, list[int]] = {}
    for kind, _, payload_class in done:
        counts[kind] = counts.get(kind, 0) + 1
        slot = by_class.setdefault(payload_class, [0, 0])
        slot[0] += 1
        slot[1] += kind == "ok"
    latencies = sorted(secs for _, secs, _ in done)
    ok = counts.get("ok", 0)
    desired, in_service = capacity
    failures = {k: v for k, v in counts.items() if k != "ok"}
    print(
        f"t+{elapsed:4d}s rate={rate:4.1f}/s done={len(done):4d} ok={100 * ok // len(done):3d}% "
        f"p50={statistics.median(latencies):5.1f}s p95={latencies[int(len(latencies) * 0.95)]:5.1f}s "
        f"| workers {in_service}/{desired} | "
        + " ".join(f"{c}:{v[1]}/{v[0]}" for c, v in sorted(by_class.items()))
        + (f" | {failures}" if failures else ""),
        flush=True,
    )


def run_ramp(
    base: str,
    compiler: str,
    asg_name: str,
    rate_start: float,
    rate_end: float,
    ramp_seconds: int,
    window: int = 60,
    tail_windows: int = 6,
) -> bool:
    """Ramp from rate_start to rate_end, returning True if it finished without aborting."""
    ramp = Ramp(base, compiler, asg_name)
    print(f"Run {ramp.run_id}: ramping {rate_start:g} -> {rate_end:g} req/s over {ramp_seconds}s against {base}")
    print(f"Start: alarms={ramp.alarm_states()} workers={ramp.capacity()}", flush=True)

    def rate_at(elapsed: float) -> float:
        return rate_start + (rate_end - rate_start) * min(1.0, elapsed / ramp_seconds)

    pool = ThreadPoolExecutor(max_workers=max(16, int(rate_end * 10)))
    started = time.time()
    pending: list[Future] = []
    aborted = None
    next_send = started
    try:
        while time.time() - started < ramp_seconds and not aborted:
            window_end = time.time() + window
            while time.time() < window_end:
                pending.append(pool.submit(ramp.one))
                next_send += 1.0 / rate_at(time.time() - started)
                time.sleep(max(0, next_send - time.time()))
            done = [f.result() for f in pending if f.done()]
            pending = [f for f in pending if not f.done()]
            if done:
                _report(int(time.time() - started), rate_at(time.time() - started), done, ramp.capacity())
            states = ramp.alarm_states()
            if any(state != "OK" for state in states.values()):
                aborted = f"the shared events table is throttling: {states}"
    except KeyboardInterrupt:
        aborted = "interrupted"
    finally:
        if aborted:
            print(f"\nABORTED: {aborted}", flush=True)
        print(f"Draining {len(pending)} in-flight request(s)...", flush=True)
        for future in pending:
            future.result()
        pool.shutdown(wait=True)

    print("=== tail: each request's unsubscribe lands about a minute later ===", flush=True)
    for i in range(tail_windows):
        time.sleep(30)
        print(f"  +{(i + 1) * 30}s alarms={ramp.alarm_states()} workers={ramp.capacity()}", flush=True)
    return aborted is None
