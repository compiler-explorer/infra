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
- [ ] Decide fix-or-accept on
      [compiler-explorer#9150](https://github.com/compiler-explorer/compiler-explorer/issues/9150):
      a worker whose events WebSocket has permanently failed still reports healthy and
      stays in the ASG doing nothing (§5.3, §5.4). Nothing below will surface this unless
      you force it in step E.
- [ ] Decide fix-or-accept on the **four-way 60s timeout stack** — CloudFront
      `origin_read_timeout`, ALB `idle_timeout`, nginx `proxy_read_timeout`, router
      `timeoutSeconds` are all exactly 60 (§2). A compile near that boundary returns a
      clean `408`, a `504`, or an HTML error page depending on scheduling jitter. Wants
      staggering (router innermost and shortest).
- [ ] Note whether
      [compiler-explorer#9148](https://github.com/compiler-explorer/compiler-explorer/pull/9148)
      has merged and reached the workers. If not, expect F-14 behaviour for API clients
      that send `application/json; charset=utf-8`.

Already fixed and needing no action: the `ce ce-router` group collision, the subscription
row TTL, and compilation queue retention (300s → 60s).

## B. Pre-flight, per environment

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
      and DynamoDB `ThrottledRequests` on `events-connections` (see §5.5).
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

## D. API compatibility

These produce a `200` with wrong output and **log nothing anywhere**, so they only ever
surface as user reports. Check them deliberately.

- [ ] No `Accept` header — record whether you get text or JSON, and decide whether the
      change from the documented default is acceptable (F-16).
- [ ] `Content-Type: application/json; charset=utf-8` with `options.userArguments` — confirm
      the flags reached the compiler by reading the asm, not the status code (F-14).
- [ ] Form-encoded POST — expected broken (F-15); confirm and decide.
- [ ] `filterAnsi` as a query param and as `backendOptions.filterAnsi` — only the query
      form is honoured (F-17).

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
- [ ] **Force #9150**: drive a worker's events WebSocket to permanent failure and confirm
      whether `/healthcheck` still returns 200 while it does no work.
- [ ] Grep the events Lambda logs for `No sender found for GUID` and
      `Failed to subscribe <conn> to <guid>` — the latter is F-04b, a silently lost
      subscription.

## F. Blue-green interaction

- [ ] Run a full `ce --env beta blue-green deploy` **with the router rule enabled**.
- [ ] Watch `Step 3.9: Clearing router cache` reach **every** in-service router. It
      tolerates partial failure and warns (§5.1,
      [infra#2372](https://github.com/compiler-explorer/infra/issues/2372)).
- [ ] After the deploy reports success, **compare the two colours' queue depths**. The old
      colour's queue being non-empty means a router is still pointed at it (F-07). This is
      a thirty-second check and the only reliable symptom.
- [ ] Confirm the newly active colour's workers picked up the right coloured queue.
- [ ] Run `ce ce-router refresh` under load; in-flight compiles should complete.

## G. Soak and load

- [ ] **Run ≥3 hours continuously** to cross API Gateway's 2-hour forced WebSocket close
      on both router and worker. Watch for a step change in timeout rate near the 2h mark.
- [ ] **Include a >10-minute idle gap**, then compile immediately — API Gateway's idle
      timeout, and the worker has no application-level liveness check (F-27).
- [ ] **Drive sustained throughput above ~3 compiles/second**, from the client side rather
      than relying on worker capacity. That is where `events-connections` write throttling
      begins (§5.5), and a throttled subscribe is silently lost and never retried. Watch
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
