# CE Router Request Path — Failure Atlas

Every branch a compilation request can take from the browser to the answer, and what
each failure looks like from the three places you can observe it: the user, the router
log, and the worker log.

Companion to `lambda_compilation_workflow.md`, which describes the happy path, and to
`ce-router-cutover-checklist.md`, which is what to actually run. This document is about
everything else that can happen.

Derived from reading, at the time of writing:

- `compiler-explorer` — `lib/compilation/sqs-compilation-queue.ts`, `lib/execution/events-websocket.ts`, `lib/base-compiler.ts`, `lib/handlers/compile.ts`
- `ce-router` (branch `build-system-routes`) — `src/compiler-explorer-router.ts`, `src/services/{result-waiter,routing,websocket-manager,http-forwarder}.ts`, `src/utils/index.ts`
- `infra` — `events-lambda/events-{sendmessage,connections}.js`, `terraform/{cloudfront,alb,apigateway_events_api,ce-router}.tf`, `terraform/modules/{blue_green,ce_router}/main.tf`, `nginx/ce-router.conf`, `init/start.sh`, `bin/lib/{blue_green_deploy,deployment_utils}.py`

Findings are marked by confidence:

- **[read]** — read directly from the code, high confidence
- **[infer]** — follows from the code but not observed running
- **[verify]** — depends on an AWS platform limit or live config; check before relying on it

---

## 1. The path, end to end

```mermaid
flowchart TD
    U[Browser / API client] -->|POST .../compile| CF[CloudFront<br/>origin_read_timeout 60s]
    CF -->|default_cache_behavior<br/>POST not cached| ALB[ALB :443<br/>idle_timeout 60s]
    ALB -->|listener rule<br/>path-pattern match| NG[nginx on router<br/>proxy_read_timeout 60s<br/>client_max_body_size 10m]
    ALB -.->|rule disabled<br/>killswitch| INST[Env instance TG<br/>legacy direct path]
    NG --> R[ce-router :10240<br/>timeoutSeconds 60]

    R -->|1. generate guid| R
    R -->|2. subscribe: guid| WS[(API Gateway WS<br/>events.compiler-explorer.com)]
    R -->|3. lookup compilerId| DDB[(DynamoDB<br/>CompilerRouting)]

    DDB -->|type=url| FWD[HTTP forward<br/>to env URL]
    DDB -->|type=queue| SQS[(SQS FIFO<br/>env-compilation-queue-COLOR)]

    SQS -->|long poll 20s<br/>MaxMessages 1| W[CE worker<br/>compilequeue.is_worker]
    W -->|delete message<br/>BEFORE compiling| SQS
    W -->|compile| W
    W -->|result or s3Key| WS
    WS -->|relay to subscribers| R
    R -->|ack: guid| WS
    WS -->|type:ack| W
    R -->|unsubscribe: guid| WS
    R --> NG --> ALB --> CF --> U

    S3R[(S3 storage.godbolt.org<br/>cache/ and cache/temp/)] -.->|fetch when s3Key only| R
    W -.->|store when >31KiB| S3R
    S3O[(S3 temp-storage<br/>sqs-overflow/)] -.->|over 256KB request| SQS
```

Two things about this picture matter more than the rest:

1. **The result does not come back the way it went out.** The request travels by SQS;
   the answer travels by WebSocket through a completely different AWS service. Either
   leg can fail independently, and the failures look nothing alike.
2. **The SQS message is deleted before the compile starts**
   (`sqs-compilation-queue.ts` — the `finally` block in `pop()`). There is no SQS
   redelivery for anything that goes wrong after pickup. **[read]**

---

## 2. The timeout stack

Four independent layers, all currently set to exactly 60 seconds:

| Layer | Setting | Source |
|---|---|---|
| CloudFront | `origin_read_timeout = 60` | `terraform/cloudfront.tf:62` (and `:193`, `:322`) |
| ALB | `idle_timeout = 60` | `terraform/alb.tf:2`, `:20` |
| nginx | `proxy_read_timeout 60s` | `nginx/ce-router.conf` |
| ce-router (queue path) | `timeoutSeconds = 60` | `src/compiler-explorer-router.ts:32` |
| ce-router (URL path) | axios `timeout: 60000` | `src/services/http-forwarder.ts` |

```mermaid
flowchart LR
    subgraph now["Now — all 60s, order undefined"]
    A1[CloudFront 60] --- A2[ALB 60] --- A3[nginx 60] --- A4[router 60]
    end
    subgraph want["Wanted — innermost fires first"]
    B1[CloudFront 75] --- B2[ALB 70] --- B3[nginx 65] --- B4[router 55]
    end
```

A compile that runs near 60s produces a **race with no defined winner**. The router
wants to answer `408 Compilation timeout` with a JSON body; whichever outer layer fires
first instead returns its own `504` with an HTML body. The same underlying event is
reported to the user in at least four different ways depending on scheduling jitter.
**[read]**

Fix is ordering, not magnitude: each layer strictly longer than the one inside it, so
the router's own error is always the one the user sees.

The URL-forwarding path shows what equal deadlines cost: its axios timeout is also 60s, so
`Request timeout to ${targetUrl}` — the one error that would name the failing target — can
never fire before an outer layer returns an HTML 504 instead. **[measured]**

---

## 3. Stage-by-stage branches

### S1 — Client → CloudFront

```mermaid
flowchart TD
    A[POST arrives at edge] --> B{WAF verdict}
    B -->|allow| C{Origin responds<br/>within 60s?}
    B -->|block| Z1[403 from edge<br/>never reaches ALB]
    C -->|yes| D[pass through]
    C -->|no| Z2[504 Gateway Timeout<br/>HTML body]
    D --> E{Origin status 503?}
    E -->|yes| Z3[custom_error_response<br/>serves /admin/503.html]
    E -->|no| F[to client]
```

| ID | Branch | Notes |
|---|---|---|
| S1.1 | WAF allows | Bot Control is currently in **count** mode (`a7ea97221`). If it is ever flipped to block, API clients are the first casualty. **[verify]** |
| S1.2 | Origin timeout | 60s, see §2. **[read]** |
| S1.3 | 503 error page | `error_caching_min_ttl = 5` with `response_page_path = /admin/503.html` (`cloudfront.tf:171-176`). POST responses are not cached, so this most likely affects GETs only — but it does mean an ALB-level 503 reaches the user as an HTML page, not a JSON error. **[verify]** |

### S2 — CloudFront → ALB → router

```mermaid
flowchart TD
    A[Request at ALB :443] --> B{ce-router listener rule<br/>path-pattern matches?}
    B -->|no / killswitch disabled| C[Default action<br/>env instance target group]
    B -->|yes| D{Healthy router targets?}
    D -->|zero| Z1[ALB 503]
    D -->|>=1| E[nginx on router]
    E --> F{Body size}
    F -->|>10MB| Z2[413 from nginx]
    F -->|<=10MB| G{ce-router process up?}
    G -->|no| Z3[502 from nginx]
    G -->|yes| H[router handler]
```

| ID | Branch | Notes |
|---|---|---|
| S2.1 | Rule matches | Patterns are `/{env}/api/compiler/*/compile`, `*/cmake`, `*/build/*` (`bin/lib/cli/ce_router.py`, `compilation_path_patterns`). Path-only — **method is not matched**, so a `GET` on those paths reaches the router and gets an Express 404. **[read]** |
| S2.2 | Killswitch off | `ce ce-router disable -e <env>` rewrites the rule to `/killswitch-disabled-<env>-*`, which never matches. Fallback is immediate. **[read]** |
| S2.3 | No healthy targets | beta and staging routers run `desired_capacity = 1` (`terraform/ce-router.tf`), so one unhealthy instance is a total compile outage for that env. **[read]** |
| S2.4 | Body limit mismatch | nginx `client_max_body_size 10m` vs. Express `limit: '16mb'`. Requests between 10MB and 16MB are rejected by nginx before the router sees them. **[read]** |
| S2.5 | Upstream keepalive | nginx sets `Connection: 'upgrade'` unconditionally, including for ordinary POSTs where `$http_upgrade` is empty. This is the classic misconfiguration that breaks upstream keepalive and produces sporadic 502s. Wants a `map $http_upgrade $connection_upgrade`. **[infer]** |

### S3 — Router: parse, guid, subscribe

```mermaid
flowchart TD
    A[handleCompilationRequest] --> B[generateGuid]
    B --> C{WebSocket connected?}
    C -->|no| Z1[500 Failed to setup<br/>result subscription]
    C -->|yes| D[send subscribe: guid]
    D --> E[sleep 50ms fixed]
    E --> F[lookupCompilerRouting]
    F --> G{routingCache hit?}
    G -->|yes| H[use cached target<br/>NO TTL - process lifetime]
    G -->|no| I{DynamoDB composite key}
    I -->|hit| J[type url or queue]
    I -->|miss| K{legacy key}
    K -->|hit| J
    K -->|miss| L[coloured queue fallback]
    I -->|error| L
```

| ID | Branch | Notes |
|---|---|---|
| S3.1 | Subscribe before routing | The router subscribes **before** it knows whether the compiler is queue- or URL-routed, so every URL-routed compile costs a wasted subscribe + unsubscribe round trip (two Lambda invocations, one DynamoDB write, one delete). **[read]** |
| S3.2 | WS down at subscribe | `send()` rejects → `500`. Every compile fails instantly while the socket is down. **[read]** |
| S3.3 | **The 50ms sleep** | `src/compiler-explorer-router.ts:228`. This is the entire defence against the subscribe/result race. See S9.2. **[read]** |
| S3.4 | **`routingCache` has no TTL** | `src/services/routing.ts` — entries are only ever removed by `clearRoutingCaches()`. The cached value is the **fully-resolved queue URL with the colour baked in**. See §5.1; this is the one I would fix first. **[read]** |

### S4 — URL-routed branch

```mermaid
flowchart TD
    A[routingInfo.type == url] --> B[unsubscribe guid]
    B --> C[axios forward to target]
    C -->|2xx| D[strip conflicting headers<br/>set content-length<br/>add CORS]
    C -->|throws| Z1[502 Failed to forward]
    D --> E{body > 1MB?}
    E -->|yes| F[log warning, send anyway]
    E -->|no| G[send]
```

| ID | Branch | Notes |
|---|---|---|
| S4.1 | **Caller's `content-length` is forwarded** | `prepareForwardHeaders` strips hop-by-hop headers but passes `content-length` through, while the body has been parsed by Express and re-serialised with `JSON.stringify`. The two lengths agree only if the caller serialised byte-identically. When ours is shorter the target blocks on bytes that never arrive, and the caller gets an HTML 504 at the 60s mark. Measured on beta: the same semantic body at 155 bytes (`json.dumps` defaults) times out, at 141 bytes (compact) returns in 0.62s. Reaches **every** URL-routed compiler — Windows, GPU, aarch64 — for any client that does not serialise like `JSON.stringify`; the CE frontend does, which is why it went unnoticed. Fixed in ce-router `0.3.0`. **Not live until instances are refreshed** — routers install `releases/latest` at boot, so a running instance keeps whatever it started with. **[measured]** |
| S4.2 | Forward timeout equals the outer deadlines | See §2. **[read]** |

Otherwise self-contained: no WebSocket, no SQS, no ack. If queue-routed compiles are broken
and URL-routed ones are fine, everything in §4 below is ruled out at once — a useful first
bisect during an incident.

### S5 — Queue-routed branch: SQS send

```mermaid
flowchart TD
    A[sendToSqs] --> B[parseRequestBody by content-type]
    B --> C[merge into messageBody<br/>set buildSystem / isCMake]
    C --> D{size > 256KB?}
    D -->|no| E[SendMessage direct]
    D -->|yes| F[PutObject to sqs-overflow/]
    F -->|ok| G[SendMessage s3-overflow ref]
    F -->|throws| Z1[500 Failed to queue]
    E --> H[MessageGroupId default<br/>MessageDeduplicationId guid]
    G --> H
    E -->|throws| Z1
```

| ID | Branch | Notes |
|---|---|---|
| S5.1 | Content-type dispatch | `parseRequestBody` treats anything without `application/json` as `{source: body}`, which is right for the documented `text/plain` form — source as the body, options in the query string — and that works through the router (measured). Form-encoded bodies never arrive here: the no-JS UI at `/noscript` posts to `/api/noscript/compile`, which has its own `express.urlencoded` route and **does not match any ce-router ALB rule** (`/{env}/api/compiler/*/…`). It bypasses the router, and prod and beta return byte-identical results. **[measured]** |
| S5.2 | Constant message group | `MessageGroupId: 'default'` for every message. FIFO allows one in-flight message per group, so receives serialise across the entire environment. Survivable because the worker deletes on pickup, not after compiling — but it is a hard throughput ceiling worth measuring before prod. **[infer]** |
| S5.3 | Dedup by guid | Fresh uuid per request, so dedup never triggers. Fine. **[read]** |

### S6 — Worker pickup

```mermaid
flowchart TD
    A[poll loop] --> B{isReadyForNewMessages?}
    B -->|no: pendingAcks > 0<br/>or WS down| C[skip, retry in poll_interval]
    B -->|yes| D[receiveMessage, 20s long poll]
    D -->|empty| C
    D -->|message| E[DELETE MESSAGE<br/>in finally]
    E --> F{s3-overflow ref?}
    F -->|yes| G[getObject]
    G -->|ok| H[compile]
    G -->|throws| Z1[request LOST<br/>already deleted]
    F -->|no| I{JSON.parse ok?}
    I -->|yes| H
    I -->|no| Z1
```

| ID | Branch | Notes |
|---|---|---|
| S6.1 | **Ack gate on pickup** | `isReadyForNewMessages()` (`events-websocket.ts:114`) requires `pendingAcks.size === 0`. Both worker threads share **one** `PersistentEventsSender`, so a single unacked result idles the whole instance. **[read]** |
| S6.2 | **Delete-before-compile** | The `finally` deletes the message as soon as it is parsed. Any failure after that point — S3 fetch, parse, compiler crash, process death — loses the request outright. No redelivery. The user waits the full 60s. **[read]** |
| S6.3 | Retention vs. timeout | Queue retention is 300s (`modules/blue_green/main.tf:18`), router timeout 60s. Messages between those ages are compiled for a client that has already given up. See §5.2. **[read]** |

### S7 — Compile

> **What `headers` means in this document.** The `headers` field on the SQS message is
> the end user's inbound **HTTP request headers**, copied verbatim by the router
> (`compiler-explorer-router.ts:217`, `const headers = req.headers`) into the message
> body as an ordinary JSON property. They are not SQS message attributes, and by the
> time the worker sees them they are just data. The worker reads exactly **one key from
> them, once** — `msg.headers['content-type']` at `sqs-compilation-queue.ts:355` — to
> re-derive a boolean the router already knew.
>
> Two consequences: (1) unlike the URL-routing path, which strips hop-by-hop headers via
> `prepareForwardHeaders` (`ce-router/src/services/http-forwarder.ts:58`), the queue path
> copies the header set wholesale, so `cookie`, `x-forwarded-for` and `user-agent` travel
> into the SQS body and, for >256KB requests, into an S3 object under
> `temp-storage.godbolt.org/sqs-overflow/`. Internal systems, so hygiene rather than an
> incident — but the worker needs one header and could be sent one. (2) a repeated header
> arrives as `string[]`, which is why `RemoteCompilationRequest.headers` is typed
> `Record<string, string | string[]>` and `isJsonContentType` takes the first value.


| ID | Branch | Notes |
|---|---|---|
| S7.1 | Unknown build system | `getRequestedBuildSystem` throws, caught, returned as a normal failed compilation naming the build system. Correct behaviour. **[read]** |
| S7.2 | Compiler not found | Throws → error result with `code: -1`. **[read]** |
| S7.3 | Request format | The format is decided from the recorded content-type by `isJsonContentType()`, which parses it the way `req.is('json')` does — parameters stripped, trimmed, lower-cased, first value if the header arrived repeated ([#9148](https://github.com/compiler-explorer/compiler-explorer/pull/9148)). A request compiles the same way whichever path it arrived by, so a caller appending `; charset=utf-8` is handled. **[read]** |

### S8 — Result sizing and `s3Key`

This is the subtlest stage. Two independent size decisions are made in two different
files against two different values.

```mermaid
flowchart TD
    A[compile finishes] --> B[base-compiler sets<br/>result.s3Key = hash]
    B --> C{store the object?}
    C -->|okToCache and not delayCaching| D[cachePut -> cache/hash]
    C -->|not okToCache and not delayCaching<br/>and >31KiB| E[tempCachePut -> cache/temp/hash]
    C -->|delayCaching<br/>project build path| F[NOTHING STORED<br/>s3Key still set]
    D --> G[worker: send decision]
    E --> G
    F --> G
    G --> H{basicResult >31KiB<br/>AND s3Key set?}
    H -->|yes| I[send s3Key only]
    H -->|no| J[send full result]
    I --> K{object actually there?}
    K -->|yes| L[router fetches, ok]
    K -->|no| Z1[NoSuchKey -> internal error text]
```

| ID | Branch | Notes |
|---|---|---|
| S8.1 | Two different measurements | `base-compiler.ts:3671-3684` measures `result` **before** `execTime`/`queueTime` are added; `sqs-compilation-queue.ts:305-318` measures `basicResult` **after**. A result sitting within a few hundred bytes of 31KiB can be judged "small, don't store" by one and "large, send by reference" by the other. **[read]** |
| S8.2 | `delayCaching` gap | The project-build path calls `afterCompilation(..., delayCaching = true)` (`base-compiler.ts:3718`), which skips **both** the cachePut and the temp store while still assigning `s3Key`. **[read]** |
| S8.3 | Failure is cosmetic-looking | The router's fallback returns a well-formed compilation result whose stderr reads `An internal error has occurred while retrieving the compilation result`. It looks like a compiler problem, not an infrastructure one. This is the shape of issue #9015; there is an untracked repro at `ce-router/test/unit/issue-9015-e2e.test.ts`. **[read]** |
| S8.4 | Oversized inline result | If a >128KB result is ever sent whole (because `s3Key` was unset), it exceeds the API Gateway WebSocket message limit. Worth confirming what the platform does with it — reject, or drop the connection. **[verify]** |

### S9 — Events Lambda relay

```mermaid
flowchart TD
    A[worker sends result object] --> B[trackGuidSender<br/>cache + dynamo 60s TTL]
    B --> C[subscribers = query GSI + cache]
    C -->|count == 0| Z1[throw No listeners<br/>501 DISCARDED by API GW]
    C -->|count >= 1| D[postToConnection each]
    D -->|410 Gone| E[remove connection<br/>return false - IGNORED]
    D -->|ok| F[router receives]
```

| ID | Branch | Notes |
|---|---|---|
| S9.1 | **The 501 goes nowhere** | `terraform/apigateway_events_api.tf` declares no `aws_apigatewayv2_route_response` for any route, so the API is one-way and the handler's `{statusCode: 501}` is discarded. From the worker's side, "nobody was listening" and "my ack got lost" are the **same event** — which is why it burns the full retry budget on both. **[read]** |
| S9.2 | Subscribe race | `subscribers()` merges a per-container in-memory cache with a GSI query. The router subscribes before it queues the work, but that orders only its own calls: `subscribe()` resolves when the frame is written to the router's socket, and the result arrives on the **worker's** connection, so the two Lambda invocations have no ordering relationship. What actually protects the subscribe is a head start — the 50ms sleep, the routing lookup, `SendMessage`, worker pickup and the compile itself, so 150-250ms at the very least. Losing it needs the subscribe invocation to stall longer than that, which in practice means a cold start. **Self-correcting**: `relay_request` throws, the worker gets no ack, and its retry 3s later re-runs `subscribers()` — by then the subscribe has landed. Costs a ~3s delay and two wasted retries, not a timeout. **[infer]** |
| S9.4 | **Subscribe silently lost** | If the subscribe's `PutItem` throws, `update()` removes the cache entry it optimistically added and rethrows; the handler returns `{statusCode: 501}`, which the one-way API discards (S9.1). The router already resolved `subscribe()` and queued the compile, so it never learns the subscription does not exist — and unlike S9.2 no retry can fix it. This is the path that produces a real 60s timeout. See §5.5 for why it is load-dependent rather than rare. **[read]** |
| S9.3 | **410 return value ignored** | `relay_request` does `await send_message(...)` and discards the boolean. A dead subscriber is indistinguishable from a delivered one. The connection is removed as a side effect, so the worker's *next* retry finds zero subscribers and takes the S9.1 path. **[read]** |

### S10 — Router receives result

```mermaid
flowchart TD
    A[ws message] --> B{text pong?}
    B -->|yes| C[heartbeat, clear pong timer]
    B -->|no| D{parses as JSON with guid?}
    D -->|no| E[warn, ignore]
    D -->|yes| F{subscriptions.get guid}
    F -->|miss| Z1[SILENTLY DROPPED<br/>no ack sent]
    F -->|hit| G[clearTimeout]
    G --> H{connected?}
    H -->|yes| I[sendAck]
    H -->|no| J[warn, swallow<br/>worker never acked]
    I --> K[markSubscriptionReceived]
    K --> L{s3Key only?}
    L -->|yes| M[fetch from S3]
    M -->|ok| N[resolve merged]
    M -->|throws| O[resolve friendly error]
    L -->|no| N
    N --> P[delete subscription]
    O --> P
    P --> Q[unsubscribe - fire and forget]
```

| ID | Branch | Notes |
|---|---|---|
| S10.1 | **Ack only inside the hit branch** | `src/services/result-waiter.ts:31` wraps `sendAck` in `if (subscription)`. Once a result has been delivered or timed out, any retransmission of that guid arrives, matches nothing, and is dropped **without an ack** — so the worker's retry is wasted even though it was delivered. **[read]** |
| S10.2 | S3 failure resolves, not rejects | The friendly error is `resolve`d, so the request returns `200` with an error inside the body rather than a 5xx. Invisible to ALB metrics. **[read]** |
| S10.3 | Unsubscribe is best-effort | Only attempted `if (this.wsManager.isConnected())`, failures logged and swallowed. Subscription rows are written with **no TTL** (`events-connections.js:106`), so every dropped unsubscribe leaks a row permanently. **[read]** |

### S11 — Ack round trip

```mermaid
flowchart TD
    A[router: ack: guid] --> B[lambda handle_ack_message]
    B --> C{getGuidSender}
    C -->|container cache hit| D[relay to sender]
    C -->|miss -> dynamo hit| D
    C -->|not found| Z1[No sender found<br/>NO ACK EVER]
    D -->|410| Z2[sender gone<br/>NO ACK EVER]
    D -->|ok| E[worker clears pendingAck<br/>instance unblocks]
```

| ID | Branch | Notes |
|---|---|---|
| S11.1 | 60s TTL on the mapping | `trackGuidSender` writes with a 1-minute TTL. Acks normally arrive in milliseconds, so this is usually fine — but note DynamoDB TTL deletion is lazy, so the row may outlive its TTL or (on a cold container) be missing from cache entirely. **[read]** |
| S11.2 | Both failure paths are silent to the worker | Same as S9.1: the worker cannot tell "no sender found" from "ack lost in transit". **[read]** |

### S12 — Worker ack handling

```mermaid
flowchart TD
    A[send result] --> B[setupAckTimeout 3s]
    B --> C{ack within 3s?}
    C -->|yes| D[resolve, unblock]
    C -->|no| E[retry, up to maxRetries 3]
    E --> C
    E -->|exhausted| F[reject, log, unblock<br/>~12s lost]
    B --> G{ws close first?}
    G -->|yes| H[pauseAckTimeouts<br/>CLEARS ALL TIMERS]
    H --> I{reconnect succeeds?}
    I -->|yes| J[retryPendingAcknowledgments<br/>resend + new timers]
    I -->|no, max attempts| Z1[pendingAcks NEVER SETTLE<br/>see 5.3]
```

---

## 4. Scenario matrix

`Heals?` means: does the system return to normal on its own, without an operator?

| ID | Trigger | User sees | Worker state | Heals? | Signal to look for |
|---|---|---|---|---|---|
| F-01 | Router WS down at subscribe | `500` instantly | unaffected | yes, on reconnect | router: `Failed to setup result subscription` |
| F-02 | Router WS flapping | intermittent `500` | unaffected | **no** — `reconnectAttempts` resets to 0 on every open, so it never exhausts and the healthcheck stays `200` | router: repeated `Persistent WebSocket connection established` |
| F-03 | Router WS max attempts exhausted | `503` from ALB | unaffected | yes — healthcheck 503 → ASG replaces | router: `Max websocket reconnection attempts` |
| F-04 | Subscribe loses the race to the result | **~3s slower than usual**, then correct | one wasted retry | yes — the retry re-runs the lookup | lambda: `No listeners for <guid>` followed by a successful relay |
| F-04b | **Subscribe `PutItem` throttled or failed** | hangs 60s → `408`/`504` | 12s stall | **no** — no retry can help, the subscription does not exist | lambda: `Failed to subscribe <conn> to <guid>`; DynamoDB `ThrottledRequests` on `events-connections` |
| F-05 | Compiler missing from routing table | normal (falls back to coloured queue) | normal | n/a | router: `No routing found for compiler` |
| F-06 | DynamoDB routing lookup fails | normal (falls back) | normal | yes | router: `Failed to lookup routing` |
| F-07 | **Stale `routingCache` after colour switch** | version skew — served by the previous deployment's code; real timeouts only after `cleanup_inactive` scales the old ASG to 0 (§5.1) | normal — it is talking to the old colour's workers | **no** — needs `/admin/clear-cache` or a process restart. The deploy now clears at Step 6.5 and says so loudly when it cannot (§5.1), so this is down to routers the clear failed to reach | old colour queue still active after a deploy; symptom that appears and vanishes across successive deploys |
| F-08 | Worker started without `--instance-color` | hangs 60s → `408`, every queue-routed request | idle, polling wrong queue | **no** | worker startup: `No instance color detected` |
| F-09 | SQS send fails | `500` | unaffected | yes | router: `Failed to send message to SQS` |
| F-10 | S3 overflow PUT fails | `500` | unaffected | yes | router: `Failed to send message to SQS` |
| F-11 | S3 overflow GET fails on worker | hangs 60s → `408` | message already deleted, request lost | per-request | worker: `Failed to fetch overflow message from S3` |
| F-12 | Malformed message body | hangs 60s → `408` | message already deleted, request lost | per-request | worker: `JSON.parse failed` |
| F-13 | Unknown build system | clean compile error naming it | normal | n/a | worker: `Unknown build system` |
| F-16 | No `Accept` header | `200` JSON where the old path returned text | normal | **no** | none |
| F-17 | `backendOptions.filterAnsi` in body | ANSI not stripped in text mode | normal | **no** | none |
| F-18 | Result >31KiB, object stored | normal | normal | n/a | router: `Fetching large compilation result from S3` |
| F-19 | Result >31KiB, **object missing** | `200` with `An internal error has occurred…` in stderr | normal | **no** | router: `Failed to fetch S3 compilation result` |
| F-20 | Project build near the 31KiB boundary | as F-19 | normal | **no** | as F-19 |
| F-21 | Ack lost (no sender found) | normal — user already got the result | **12s stall** | yes, after 12s | lambda: `No sender found for GUID` |
| F-22 | Ack lost (sender 410) | normal | 12s stall | yes | lambda: `Failed to send ack … disconnected` |
| F-23 | Result delivered, router 410 | hangs 60s → `408` | 12s stall | per-request | lambda 410 in `send_message` |
| F-24 | Retransmission after delivery | normal | **12s stall, guaranteed** — router never re-acks (S10.1) | yes, after 12s | worker: `Max retries (3) reached` |
| F-25 | Compile finishes after router gave up | already `408` | 12s stall | yes | lambda: `No listeners` |
| F-26 | Queue backlog >60s deep | widespread `408` | most instances stalling on orphans | **eventually**, but recovery is slowed by the stalls | SQS `ApproximateAgeOfOldestMessage` > 60 |
| F-27 | **Worker WS half-open** | hangs 60s → `408`, repeatedly | sends into the void, no liveness check (§5.4) | **no** | silence — no error is logged anywhere |
| F-28 | Worker WS permanently failed | queue backs up | **zombie: healthy but doing nothing** (§5.3, §5.4) — [compiler-explorer#9150](https://github.com/compiler-explorer/compiler-explorer/issues/9150) | **no** | worker: `Max websocket reconnection attempts`, then nothing |
| F-29 | Worker killed mid-compile | hangs 60s → `408` | request lost (deleted at pickup) | per-request | none on the worker |
| F-30 | Router restarted | in-flight requests fail | orphaned results → stalls | yes | router restart in Papertrail |
| F-31 | Blue/green switch, cache clear OK | normal | normal | n/a | deploy: `Router cache cleared successfully` |
| F-32 | Blue/green switch, cache clear **failed** | as F-07 | idle | **no** (deploy log's "expires in 30s" is wrong — see §5.1) | deploy: `Failed to clear router cache` |
| F-33 | Body 10–16MB | `413` from nginx | unaffected | n/a | nginx error log |
| F-34 | Response >1MB | usually fine | normal | n/a | router: `exceeds 1MB - may cause ALB issues` |
| F-35 | Compile near 60s | `408`, `504`, or an HTML error page — undefined which | normal | n/a | mismatch between router and ALB status codes |
| F-36 | No healthy routers | ALB `503` → CloudFront HTML page | unaffected | yes, via ASG | target group healthy count = 0 |
| F-37 | `GET` on a router path | Express `404` | unaffected | n/a | router access log |
| F-38 | URL-routed target down | `502 Failed to forward` | n/a (no queue involved) | depends on target | router: `URL forwarding error` |
| F-38b | **URL-routed, caller's JSON not byte-identical to `JSON.stringify`** | hangs 60s → HTML `504` | n/a | **no** — deterministic per client | no router log line at all; the forward starts and never completes (S4.1) |
| F-40 | nginx keepalive breakage | sporadic `502` | unaffected | per-request | nginx error log, no matching router log |

---

## 5. The traps

These are the ones that do not self-heal, ordered by how much damage they do.

### 5.1 The fallback the invalidation design assumes does not exist

The design here is push invalidation: the deploy calls `POST /admin/clear-cache`, and
two comments in the router agree on what that is for —

- the `/admin/clear-cache` endpoint: *"eliminates the 30s cache TTL delay"*
- `clearRoutingCaches()`: *"without waiting for the 30-second cache TTL to expire"*

So: push for speed, with a 30-second TTL as the fallback. That is a sound design — **if
the fallback exists**.

It does not, because `routingCache` stores a value **derived from the volatile input**
rather than the input itself:

```ts
const queueName = item.queueName?.S;           // stable
const activeColor = await getActiveColor();    // volatile — changes every deploy
const queueUrl = buildQueueUrl(queueName, activeColor);
routingCache.set(cacheKey, {type: 'queue', target: queueUrl, ...});  // resolved, cached forever
```

An entry that is correct when written becomes wrong the moment SSM changes. Nothing needs
to watch SSM — the push is meant to cover that — but the entry has to be recoverable
without the push, and it isn't.

`routingCache.get()` returns before `getActiveColor()` is ever reached, so once a
compiler has been looked up on a router, that router's colour TTL can never fire for it
again. The fallback is unreachable code, and a push is silently the **only** mechanism —
while both comments above assert otherwise.

The push is as good as a push gets — [infra#2372](https://github.com/compiler-explorer/infra/issues/2372)
made it all-or-nothing, retried, and present on the rollback path — but it is still a
push, and a router it cannot reach has nothing else to fall back on.

There is no second signal — no EventBridge rule on the SSM parameter, no SNS to the
routers; `/admin/clear-cache` is one of only two non-compile endpoints the router has.

**When the clear runs matters as much as whether it runs.** Because `queueName` is
stored uncoloured (`"prod-compilation-queue"`), the colour is appended from
`getActiveColor()` at lookup time, and `clearRoutingCaches()` wipes `activeColorCache`
too — so a clear that runs before `_update_ssm_parameters` empties the cache at the one
moment when the only value available to refill it is the stale one. The same holds for
`update_compiler_routing_table`, which mutates rows the routers have already cached.

The clear is therefore Step 6.5, after both, and on the rollback path. It requires every
in-service router, retrying each before giving up, clears out-of-service routers
opportunistically, and prints the by-hand command for any it missed.

**The symptom is not an outage.** The deploy deliberately leaves the old ASG running
("Old {color} ASG remains running for rollback if needed"), and that ASG scales on its
own colour's queue depth — so a poisoned router's messages land on a queue that still has
consumers, and the requests **succeed, served by the previous deployment's code**, while
the deploy reports success. Timeouts arrive later, when the old ASG scales in
(`min_size` is now 0) or the next deploy reuses that colour. The breakage therefore
surfaces at a deploy unrelated to the one that caused it.

The cache is keyed `{env}#{compilerId}` per router process, so this is never all-or-
nothing: the same compiler can succeed on one router and fail on the next.

**The fix is not a TTL on `routingCache`** — that adds a second mechanism to paper over
a broken first one. Cache the routing *decision* (`type`, plus `queueName` or
`targetUrl`) and resolve the colour at send time from `getActiveColor()`. That adds no
new machinery; it makes the fallback the code already documents actually reachable.
Afterwards both comments above become true: everything cached is stable,
a missed push costs at most 30 seconds, and `/admin/clear-cache` is the optimisation it
was written to be.

What the cache buys today is one DynamoDB `GetItem` per compile on a small table —
noise next to an SQS round trip, a compile, and the three `events-connections` writes
from §5.5.

**The colour is not the only stale thing.** `update_compiler_routing_table()` at Step 6
mutates existing rows: a compiler whose `routingType` flips between `queue` and `url`, or
whose `targetUrl` or `queueName` changes, is cached wholesale in every router. Resolving
the colour at send time does **not** fix that, which is why the invalidation has to come
after Step 6 rather than merely after the switch.

**How bad is it in practice? Less than it looks.** Blue and green run the same compiler
inventory apart from whatever the deploy adds, so a stale router still reaches workers
that can compile everything in its cache — that set is exactly what it looked up before
the switch, all of which exists on both colours. A genuinely new compiler has no cache
entry, so it takes a fresh lookup and routes correctly; and a user cannot request one
until their client has the new compiler list, which needs a reload slower than the
switch itself.

So the steady-state effect is **version skew, not failure**: a fraction of traffic quietly
served by the previous deployment's code. That ranks §5.1 below §5.3/§5.4 and §5.5.

Two things still bite:

- **`cleanup_inactive()` makes it real.** It does `reset_asg_min_size(asg, 0)` then
  `scale_asg(asg, 0)` — an explicit scale to zero. A stale router's messages then land on
  a queue with no consumers and time out at 60s. Same during the next deploy's instance
  replacement. The failure is therefore **operator-triggered and decoupled in time** from
  the deploy that caused it: a routine cleanup starts timing out compilations for reasons
  that trace back days.
- **It oscillates.** With alternating deploys a router stuck on `blue` is wrong while
  green is active and accidentally correct after the next switch back, so the symptom
  appears and vanishes without anyone touching the routers.

Cycling the routers on every deploy would also clear all of this, and is ruled out: the
restart path adds 502s on single-router environments and an instance refresh adds 10-15
minutes to every deploy, neither of which is worth it at this severity. Restarting one
router by hand remains the recovery for a stale one.

Note the exposure is bounded: `active-color` is written only by `_update_ssm_parameters`,
called only from `switch_target_group`, called only by the deploy (`:550`) and the
rollback (`:686`). This is a deploy-procedure risk, not a random-failure one.

Filed as [compiler-explorer/infra#2372](https://github.com/compiler-explorer/infra/issues/2372).
**[read]; the scale-in half is [infer] — confirm the old ASG's instance count after a
switch**

#### What is left

A router the push does not reach stays stale until its process restarts, with the same
consequences as above: version skew normally, real timeouts once `cleanup_inactive`
scales the old ASG to zero, oscillation across alternating deploys. It is rare — it takes
a router unreachable through the retries — but it is *as permanent as ever* when it
happens, which is why the deploy shouts about a partial clear and names the command to
run rather than warning that the cache expires by itself.

Closing it means stopping `routingCache` from baking in the colour: cache the decision
(`type`, plus `queueName` or `targetUrl`) and resolve the colour at send time. That makes
a miss self-healing within 30s instead of permanent, because it is what finally makes the
documented fallback reachable.

### 5.2 Retention outlives the deadline — fixed

Queue retention was 300s against the router's 60s timeout, leaving a 240s window in which
a message was still deliverable but no longer wanted. A message picked up in that window
was compiled normally, its result found no subscriber (S9.1), and because the events API
is one-way the worker could not be told — so it burned its full ack-retry budget, ~12s,
during which that instance pulled nothing. Each expired message therefore cost a wasted
compile *plus* a stall.

**Fixed**: retention is now 60s (also the SQS minimum), matching the router's deadline, so
a message that cannot be answered is dropped by SQS rather than compiled for nobody.
`modules/blue_green/main.tf` carries a comment tying the two numbers together.

Residual: a message picked up just under the deadline still produces a late result, so the
window is bounded by compile time rather than eliminated. That is as tight as SQS allows.
The stall itself is addressed independently by
[compiler-explorer#9150](https://github.com/compiler-explorer/compiler-explorer/issues/9150)
(decoupling polling from `pendingAcks`), and a nack on zero subscribers would let the
worker give up immediately instead of retrying into a void. **[fixed]**

### 5.3 `pendingAcks` can never settle

In `events-websocket.ts`:

- `ws.on('close')` → `pauseAckTimeouts()`, which **clears every pending timer** without
  rescheduling
- `scheduleReconnect()` at max attempts → sets `hasPermanentlyFailed`, calls
  `rejectQueuedMessages()` — which drains `messageQueue` **only**

`pendingAcks` is never rejected on that path. Its entries keep their (now cleared)
timers and their promises never settle, so `pendingAcks.size` stays above zero forever,
so `isReadyForNewMessages()` returns false forever, so the worker never polls again.

Combined with 5.4 below, that instance stays in the ASG reporting `200 OK`
indefinitely. Filed with 5.4 as
[compiler-explorer#9150](https://github.com/compiler-explorer/compiler-explorer/issues/9150).
**[read]**

### 5.4 Worker health is computed and thrown away

`startCompilationWorkerThread` returns `() => !persistentSender.hasFailedPermanently()`
(`sqs-compilation-queue.ts:506`). `lib/app/main.ts:173` calls it as a statement and
discards the return value. `HealthcheckController.setCompilationWorkerHealthCheck`
(`healthcheck-controller.ts:48`) has **zero callers** in the repository — the field
keeps its `() => true` default forever.

Same for `setExecutionWorkerHealthCheck`.

One line in `main.ts` closes it — filed as
[compiler-explorer#9150](https://github.com/compiler-explorer/compiler-explorer/issues/9150),
which also covers §5.3. Note the wiring does **not** cover a flapping socket (F-02):
`reconnectAttempts` resets on every successful open, so it never trips the flag.
**[read]**

### 5.5 The events table is the only provisioned one, and it gates every compile

`events-connections` is the sole DynamoDB table in the stack on `PROVISIONED` capacity —
every other table is `PAY_PER_REQUEST` (`terraform/dynamodb.tf:135`). Baseline 10 WCU,
autoscaling to a max of 50; `SubscriptionIndex` is on the same 10 → 50.

Each queue-routed compile writes:

| Write | Table | GSI |
|---|---|---|
| `subscribe` PutItem | 1 | 1 |
| `trackGuidSender` PutItem | 1 | 0 (sparse — no `subscription` attribute) |
| `unsubscribe` DeleteItem | 1 | 1 |
| **per compile** | **3 WCU** | **2 WCU** |

The table binds first: roughly **3 compiles/second at baseline and 16/second at the
ceiling**, with target-tracking autoscaling reacting in minutes. Insufficient GSI write
capacity throttles base-table writes too, so the GSI is a second gate on the same budget.

A throttled subscribe is not retried and not reported (S9.4), so above that ceiling a
fraction of compiles simply have no subscriber — each costing a 12s worker stall and a
60s user-visible hang. It is self-reinforcing: the stalls cut throughput, the queue
lengthens, more requests pass their deadline.

On the read side, `EventsConnections.remove()` does a full-table `ScanCommand` on every
disconnect, and API Gateway's 2-hour maximum connection duration guarantees disconnects
happen whether or not anything goes wrong. At 27.5 KB that reads roughly 4 RCU against
the 25 RCU baseline, so it is noise today — worth revisiting only if the table grows by
orders of magnitude. The cheap version, if it ever matters: on a 410 in `relay_request`
both the connectionId and the guid are known, so that one row can be deleted directly
instead of calling `remove()`.

This is pre-existing, but the cutover multiplies writes to this table by the share of
traffic it moves — compiles served directly over HTTP today do no subscribe, no
unsubscribe and no guid-sender tracking. **[read] + [verify the arithmetic against
`ConsumedWriteCapacityUnits` and `ThrottledRequests` before trusting the numbers]**

---

## 6. Reverse index: symptom → candidates

Start here during an incident.

**User sees `500`** → F-01 (WS down at subscribe) · F-09/F-10 (SQS or S3 write) · F-38 (URL forward)

**User sees `408`** → F-04b (subscribe lost to throttling — check `ThrottledRequests` on `events-connections` first, see §5.5) · F-07/F-08/F-32 (wrong queue — check queue depth by colour first) · F-11/F-12 (message lost at pickup) · F-25/F-26 (backlog) · F-27 (half-open worker socket) · F-29 (worker died mid-compile)

**User sees `502`/`504`/HTML error page** → F-35 (timeout race, §2) · F-36 (no healthy routers) · F-40 (nginx keepalive)

**User sees `200` but the output is wrong** → F-14 (charset dropped the flags) · F-16/F-17 (Accept / filterAnsi). None of these log anything; they only surface as user reports.

**Anything under `/api/noscript/…`** → not the router. The no-JS UI has its own endpoint, outside the ALB rules; rule it out before investigating.

**User sees `An internal error has occurred while retrieving the compilation result`** → F-19/F-20. Always the `s3Key`-without-an-object path (§S8). Not a compiler problem.

**Throughput collapsed, no errors** → F-24/F-21 (ack stalls) · F-28 (zombie worker) · §5.3. Check `pendingAcks` behaviour before suspecting the compilers.

**Deploy reported success but some results look stale** → F-07 (§5.1): a router is still pointed at the old colour's queue, whose workers are deliberately left running. Compare the two colours' queue depths after a deploy.

**One environment broken, others fine** → F-07/F-08/F-32. Compare the worker's polled queue URL against SSM `/compiler-explorer/<env>/active-color`.

**URL-routed compilers hang for one client but work in the browser** → F-38b (S4.1): the caller's `content-length` no longer matches the re-serialised body. Retry the same request with compact JSON to confirm.

**Queue-routed broken, URL-routed fine** → everything in §4 that involves SQS or the WebSocket. Use §S4 as the bisect.

---

## 7. Cheapest fixes, in order

| Fix | Where | Removes |
|---|---|---|
| Wire the worker healthcheck — [#9150](https://github.com/compiler-explorer/compiler-explorer/issues/9150) | `lib/app/main.ts:169`, `:173` | F-28, makes §5.3 self-correcting |
| Reject `pendingAcks` on permanent failure — [#9150](https://github.com/compiler-explorer/compiler-explorer/issues/9150) | `lib/execution/events-websocket.ts`, `scheduleReconnect` | §5.3 |
| Stop baking the colour into `routingCache`; resolve it at send time | `ce-router/src/services/routing.ts` | restores the fallback the code already documents (§5.1) |
| Stagger the four timeouts | `cloudfront.tf`, `alb.tf`, `nginx/ce-router.conf`, router | F-35 |
| Ack outside the `if (subscription)` | `ce-router/src/services/result-waiter.ts:31` | F-24 (the delivered-but-unmatched window only) |
| Move `events-connections` to `PAY_PER_REQUEST` | `terraform/dynamodb.tf:135` | F-04b, §5.5 — the only provisioned table in the stack |
| Nack on zero subscribers | `events-lambda/events-sendmessage.js`, `relay_request` | F-25 retry waste |
| Decouple polling from `pendingAcks` | `lib/execution/events-websocket.ts:114` | F-21…F-25 stalls generally |
| Application-level ping on the worker | `lib/execution/events-websocket.ts:183` | F-27 |

The first four are small, independent, and each removes a failure mode that does not
self-heal. They are worth doing before the cutover rather than after.
