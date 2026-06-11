# Querying Papertrail logs via the SolarWinds Observability API

All CE instances forward syslog to Papertrail, which is part of SolarWinds Observability.
Besides the web UI, logs can be searched programmatically — useful for incident forensics,
counting log volume, or correlating events across the fleet.

## Access

- Create an API token in SolarWinds Observability (Settings → API Tokens) and store it
  somewhere private, e.g. `~/.swo_token` (mode 0600).
- Endpoint: `https://api.na-01.cloud.solarwinds.com/v1/logs` (`na-01` is our org's data cell; other SolarWinds accounts may be on `na-02`, `eu-01`, etc.)

## Basic query

```bash
curl -s -H "Authorization: Bearer $(cat ~/.swo_token)" \
  'https://api.na-01.cloud.solarwinds.com/v1/logs?filter=host%3Aip-172-30-0-63%20%22temp%20cleanup%20skipped%22&startTime=2026-06-11T09:55:00Z&endTime=2026-06-11T13:35:00Z&pageSize=1000&direction=forward'
```

Parameters:

- `filter` — Papertrail-style search syntax: bare words, quoted phrases, `host:<name>`,
  boolean `OR`, `-` for negation, parentheses for grouping.
- `startTime` / `endTime` — ISO 8601 (UTC).
- `pageSize` — maximum 1000.
- `direction` — `forward` or `backward`.

The response contains a `logs` array (each entry: `time`, `hostname`, `program`,
`severity`, `message`) and `pageInfo.nextPage`, a ready-made path for the next page.
To count log volume, paginate and sum — busy fleet-wide minutes far exceed one page.

## Gotchas

- The API sits behind a WAF that rejects Python urllib's default `User-Agent` with
  HTTP 403; send a curl-like `User-Agent` header from scripts.
- Log ingestion has a monthly subscription quota. A runaway instance can exhaust it and
  SolarWinds then **stops ingesting for the whole fleet** until support resets it or the
  cycle rolls over. This happened on 2026-06-11: a disk-full instance's rsyslog write-error
  feedback loop shipped ~27M messages in 95 minutes (~290k/minute), hitting 315% of quota
  (see compiler-explorer/compiler-explorer#8811 and the rsyslog forwarding guard in
  `setup-common.sh`). The Grafana metrics pipeline is separate and unaffected by log quota.
- ANSI colour escape sequences from CE's logger appear verbatim in `message`; strip
  `\x1b\[[0-9;]*m` before processing.
