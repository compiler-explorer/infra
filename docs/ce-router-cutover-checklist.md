# CE Router Cutover Checklist

For enabling CE Router routing on beta and staging, and eventually prod. Companion to
`ce-router-failure-atlas.md`, which explains the mechanisms; `F-nn` and `§n.n` references
below point into it.

Tick through this; do not read it as background.

---

## A. Before you start

- [ ] `ce ce-router --help` on the machine you will operate from lists **both** `enable`
      and `disable`. (The two-groups collision that could hide them is fixed, but confirm
      on your machine — this is the rollback lever.)
- [ ] Run `ce ce-router disable -e beta` once, before enabling anything, so the rollback
      path is known-good rather than assumed.
- [ ] Decide fix-or-accept on the **four-way 60s timeout stack** — CloudFront
      `origin_read_timeout`, ALB `idle_timeout`, nginx `proxy_read_timeout`, router
      `timeoutSeconds` are all exactly 60 (§2). A compile near that boundary returns a
      clean `408`, a `504`, or an HTML error page depending on scheduling jitter. Wants
      staggering (router innermost and shortest).

Already fixed, deployed and confirmed by a beta smoke run: the `ce ce-router` group
collision, the subscription row TTL, compilation queue retention (300s → 60s), the
URL-forwarding `content-length` bug (ce-router `0.3.0`), and compiler-explorer#9148 and
#9149. compiler-explorer#9151 is merged but can only be confirmed by section E.

## B. Pre-flight, per environment

### B0. Make sure the environment has workers at all

**Beta and staging sit at zero instances when idle** (`min_instances` is 0 for everything
but prod), and their ASGs scale on compilation queue depth. That scaling cannot rescue a
cold environment within a request's lifetime: `health_check_grace_period` is 240s and
compiler registration is allowed up to 600s, against a router deadline of 60s. So the
first compiles after an idle period **always** time out, and go on failing for minutes
while an instance boots.

Every check below is a false negative until this is done.

- [ ] `ce --env <env> blue-green status` — confirm an ASG has instances **InService**.
      If not, `ce --env <env> environment start` (or a deploy) and wait.
- [ ] Wait for compiler registration to finish, not just for the instance to be InService.
      An instance that is InService but still discovering compilers answers 404.
- [ ] Confirm with a single hand-run compile before running the suite.

> At time of writing `beta-blue` and `beta-green` are both at 0/0 while the beta ALB rule
> is **enabled** (priority 72, real compile paths). Beta compilations therefore go
> router → SQS → nobody and time out. Either scale beta up before testing, or disable the
> rule while it is unused — an enabled rule in front of an empty environment looks exactly
> like a broken router.

### B1. Routing and health

- [ ] `ce ce-router status` — target group exists, rule present, healthy targets ≥ 1
      (beta/staging) or ≥ 2 (prod).
- [ ] `ce ce-router version` — every instance on the version you intend to test.
- [ ] `ce ce-router instances` — ASG capacity and per-instance health as expected.
- [ ] `curl http://<router-private-ip>/healthcheck` on each: `websocket: "connected"`,
      `secondsSinceLastActivity` small.
- [ ] On each **worker**: confirm the polled queue URL carries the colour and matches SSM
      `/compiler-explorer/<env>/active-color`. Grep the startup log for `Instance color:`
      versus `No instance color detected` — the latter is a silent 100% failure (F-08).
- [ ] Confirm `compilequeue.is_worker=true` and `compilequeue.events_url` for the env.
- [ ] Record baselines: SQS `ApproximateNumberOfMessagesVisible` and
      `ApproximateAgeOfOldestMessage` per colour, ALB target 5xx, `ce_sqs_compilations_total`,
      and DynamoDB `ThrottledRequests` on `events-connections` (see §5.3).
- [ ] Capture the latency profile via the current non-router path, for a before/after.

## C. Functional matrix

Run each as the browser frontend **and** as `curl`.

- [ ] Plain compile, small output, queue-routed compiler.
- [ ] **The same compile again immediately** — the cache-hit path returns in milliseconds
      and is the tightest subscribe race (S9.2). Loop it 50× and confirm no timeouts.
- [ ] Compile with execution (`filters.execute`) — exercises the separate execqueue
      WebSocket path alongside.
- [ ] `POST /<env>/api/compiler/:id/cmake` (legacy spelling).
- [ ] `POST /<env>/api/compiler/:id/build/:buildSystem` for each supported build system,
      plus one **unknown** id — must surface as a failed compilation naming it, not a 500.
- [ ] URL-routed compiler (GPU / Windows / aarch64) — response identical to the
      non-router path.
- [ ] A compiler **absent** from the routing table — must fall back to the coloured queue
      and still work.
- [ ] Large **request** >256KB → S3 overflow; confirm the object is created and fetched.
- [ ] Large **result** >31KiB → the `s3Key` path, specifically:
  - [ ] with `bypassCache` set
  - [ ] from a **project build** (the `delayCaching` path)
  - [ ] sized within ~1KB of 31KiB
      Any `An internal error has occurred while retrieving the compilation result` is a
      fail (F-19/F-20, §S8).
- [ ] Response >1MB — confirm the client receives it intact.

### Running section C automatically

```
ce --env beta ce-router smoke                      # picks compilers itself
ce --env beta ce-router smoke --compiler g132      # or name one
ce --env beta ce-router smoke --skip-slow          # omit the oversized/boundary checks
```

Exits non-zero if any check fails. It asserts on what the caller receives rather than on
status codes, because several of these failures return HTTP 200 with a broken body — the
`s3Key` one in particular.

Compilers are chosen by **language**, not from the routing table alphabetically: that lands
on ids like `386_gl114`, an i386 Go compiler, which cannot build the C++ these checks send.
Every size-dependent check then measures an empty result and passes while testing nothing.
The URL-routed candidate is filtered the same way.

### Prod baseline — legacy direct path

Recorded with prod killswitch-disabled (`/killswitch-disabled-prod-*`), so this is the
**non-router** path: what correct looks like. Beta was already live on the router when this
was taken, so a beta run is directly comparable.

`ce --env prod ce-router smoke --iterations 20`, compilers `g132` (queue) and
`cl19_2015_u3_32_exwine` (URL):

| Check | Result | Time |
|---|---|---|
| plain compile | `code=0 asm=105B` | 0.44s |
| cache-hit loop x20 | 20/20 ok, slowest 0.33s | 3.35s |
| compile with execution | `code=0 asm=194B` | 0.59s |
| cmake (legacy spelling) | `code=0 asm=0B` | 0.69s |
| build/cmake | `code=0 asm=0B` | 0.23s |
| unknown build system | 404 naming it | 0.12s |
| URL-routed compiler | `code=2 asm=259B` | 0.55s |
| large result (s3Key path) | `code=0 asm=235006B` | 2.58s |
| large result + bypassCache | `code=0 asm=235006B` | 1.23s |
| large result from project build | `code=0 asm=0B` | 0.83s |
| large request (258KB, S3 overflow) | `code=0 asm=16701B` | 0.55s |
| 31KiB boundary sweep | all sizes usable | — |
| response over 1MB | `code=0 asm=2212181B` | 7.86s |

**13/13 passed.** Three things to read correctly when comparing:

- **Two checks are path-dependent.** An unknown build system is a **404** on the direct path
  (`compile.ts:566`) but a **failed compilation naming it** via the router, because the
  worker throws. The check accepts either; only a silent success would be wrong.
- **`code=2` on the URL-routed compiler is not a routing failure.** MSVC-under-wine rejecting
  the default flags still proves the forward path works — a well-formed result came back.
- **The cmake checks return `asm=0B`.** Recorded as observed, not asserted as correct: the
  build succeeds but yields no disassembly with these filters. Compare like-for-like rather
  than treating a non-zero value on the router path as a regression.

Latency here is the direct path with no queue hop. Expect the router path to be slower;
what matters is that nothing fails and the cache-hit loop stays clean, since that loop is
the tightest subscribe/result race.

A run against an environment with no workers fails every check with a 60s timeout, which
looks identical to a broken router. Do B0 first.

### Beta result — router path

`ce --env beta ce-router smoke --iterations 20`, beta-green, ALB rule priority 72 active,
ce-router `0.5.0`, workers carrying compiler-explorer#9148/#9149/#9151.

**17/17 passed.** Beta through the router now matches prod's direct path on every check in
the suite, including all three `s3Key` variants, the 258KB overflow request, the 2.1MB
response and the boundary sweep. Latency is comparable — the cache-hit loop's slowest was
0.93s against prod's 0.33s, which is the queue hop.

Everything the first run caught has since been fixed and confirmed by a later run:

| Check | First run | Now | Fixed by |
|---|---|---|---|
| URL-routed compiler | `HTTP 504` after 60.04s | sub-second | ce-router `0.3.0` |
| charset keeps user arguments | flags silently dropped | `-D` reached the compiler | [#9148](https://github.com/compiler-explorer/compiler-explorer/pull/9148) |
| oversized result keeps execution output | 229KB of asm, `execResult={}` | output survived | [#9149](https://github.com/compiler-explorer/compiler-explorer/pull/9149) |
| no `Accept` header returns text | `application/json` | `text/plain` | ce-router `0.5.0` |

Those four print `[FIXED]` rather than `[PASS]` because they carry a tracking link; that is
the mechanism working, not a warning. One going back to `[KNOWN]` means a regression or a
rollback.

**Not covered by the suite**: compiler-explorer#9151 (a worker reporting unhealthy once its
events WebSocket has given up) cannot be confirmed from outside — it needs the failure
injection in section E.

## D. API compatibility

This is where the router can return a `200` with wrong output and **log nothing anywhere**,
so these only ever surface as user reports. Two are covered by `ce ce-router smoke` and pass
(section C); the rest are by hand.

- [x] No `Accept` header — automated, passing. Returns `text/plain`, matching the
      documented default and the direct path, since ce-router `0.5.0`.
- [x] `Content-Type: application/json; charset=utf-8` — automated, passing. The caller's
      flags reach the compiler since
      [compiler-explorer#9148](https://github.com/compiler-explorer/compiler-explorer/pull/9148).
- [x] Form-encoded POST — **not affected by the cutover**. Form bodies go to
      `/api/noscript/compile` (the `/noscript` UI), which has its own `express.urlencoded`
      route and matches no ce-router ALB rule, so it never reaches the router. Verified
      identical on prod and beta.
- [ ] `filterAnsi` as a query param and as `backendOptions.filterAnsi` — only the query
      form is honoured (F-17). Needs a compile that emits ANSI, so it is fiddly to automate,
      and it is the last unverified item in this section.

## E. Failure injection

- [ ] **Kill the router's WebSocket mid-flight.** Expect a heartbeat timeout, reconnect,
      `Resubscribing to N pending subscriptions`, and in-flight compiles still answered.
- [ ] **Flap it repeatedly.** `reconnectAttempts` resets on every successful open, so a
      flapping socket never exhausts its budget and never fails the healthcheck while
      returning 500s (F-02). Confirm what the target group does.
- [ ] **Force an unacked result** — kill the router before a result arrives and let the
      worker retransmit. Measure how long that instance stops pulling (F-24).
- [ ] **Force an orphaned result** — pause a worker past the router's deadline. Now that
      retention is 60s this should be much rarer; confirm. Not pass/fail — measure, and
      record whether the worker can distinguish "nobody listening" from "ack lost" (it
      cannot, S9.1).
- [ ] **Restart a worker mid-compile** — in-flight requests should 408 cleanly, not 502.
- [ ] **Restart a router under light load** — brief on single-router environments.
- [ ] Drive a worker's events WebSocket to permanent failure and confirm `/healthcheck`
      now returns 500 rather than 200 (compiler-explorer#9151). A *flapping* socket is
      still not covered — `reconnectAttempts` resets on every open, so it never trips the
      counter (F-02).
- [ ] Grep the events Lambda logs for `No sender found for GUID` and
      `Failed to subscribe <conn> to <guid>` — the latter is F-04b, a silently lost
      subscription.

## F. Blue-green interaction

**A colour switch no longer tests the cache clear.** Since ce-router `0.4.0`, `routingCache`
holds the routing *decision* and the colour is resolved per request from `activeColorCache`,
whose 30-second TTL is reachable — so a router that misses the clear entirely self-heals its
colour within 30s. Any check run more than half a minute after the switch will pass whether
or not Step 6.5 ran. The clear is still load-bearing, but only for the **routing-table**
half, which is cached with no expiry.

- [x] Run a full `ce --env beta blue-green deploy` **with the router rule enabled** — done
      2026-09-23. Router had been up since the previous day, so it carried a warm cache
      through the switch; both queues drained and the suite ran 17/17 afterwards.
- [ ] Watch `Step 6.5: Clearing router cache` in the deploy output. This is the **only**
      direct evidence the clear ran — `✓ Router cache cleared on all N in-service routers`
      versus the `❌ ROUTER CACHE NOT CLEARED` block. A partial clear leaves the missed
      routers holding stale *routing-table* entries until they are cleared by hand (§5.1,
      [infra#2372](https://github.com/compiler-explorer/infra/issues/2372)).
- [ ] To exercise what the clear is now for, deploy across a **routing-table change** — a
      compiler whose `routingType`, `targetUrl` or `queueName` moves, which Step 6's
      `update_compiler_routing_table` will write. A router that misses the clear keeps the
      old decision indefinitely; nothing expires it.
- [ ] Compare the two colours' queue depths after the deploy. No longer proves the clear
      ran, but still catches a **worker** polling the wrong colour (F-08), which is a
      silent 100% failure for queue-routed compilers.
- [ ] Confirm the newly active colour's workers picked up the right coloured queue.
- [ ] Run `ce ce-router refresh` under load; in-flight compiles should complete.

## G. Soak and load

- [ ] **Run ≥3 hours continuously** to cross API Gateway's 2-hour forced WebSocket close
      on both router and worker. Watch for a step change in timeout rate near the 2h mark.
- [ ] **Include a >10-minute idle gap**, then compile immediately — API Gateway's idle
      timeout, and the worker has no application-level liveness check (F-27).
- [ ] **Drive sustained throughput above ~3 compiles/second**, from the client side rather
      than relying on worker capacity. That is where `events-connections` write throttling
      begins (§5.3), and a throttled subscribe is silently lost and never retried. Watch
      `ThrottledRequests` — it moves before the 408s do.
- [ ] Run the load test at **one worker and at three or more**. Beta and staging default to
      one, which is the worst case for ack stalls and not representative of prod.
- [ ] Watch whether SQS receive throughput plateaus — `MessageGroupId` is a constant, so
      FIFO serialises receives environment-wide.

## H. What to watch throughout

| Where | Signal |
|---|---|
| Worker logs | `No acknowledgment for <guid>, retry` · `Max retries (3) reached` · `Skipping message pull - WebSocket not ready` |
| Events Lambda | `No listeners for <guid>` · `No sender found for GUID` · `Failed to subscribe` |
| Router (Papertrail `router.<env>`) | `WebSocket heartbeat timed out` · `Compilation timeout` · `Failed to setup result subscription` |
| CloudWatch SQS | `ApproximateAgeOfOldestMessage` — the leading indicator |
| CloudWatch DynamoDB | `ThrottledRequests` on `events-connections` and `SubscriptionIndex` |
| ALB | target 5xx, `TargetResponseTime` p99, unhealthy host count |
| Prometheus | `ce_sqs_compilations_total` rate vs. the pre-switch baseline |

There are no Grafana alerts covering the router or the compilation queues, and the router
exposes no Prometheus endpoint — this is manual watching. An
`ApproximateAgeOfOldestMessage` alert is worth adding before staging.

## I. Rollback

- [ ] `ce ce-router disable -e <env>` — verified in step A, before you need it.
- [ ] Confirm traffic falls back within seconds and compiles succeed on the old path.
- [ ] Confirm no in-flight requests are lost during the flip.
- [ ] Expect a brief burst of `No listeners` and worker stalls right after disabling, as
      already-queued messages are compiled for routers that have stopped waiting. That is
      the drain, not a new fault.
