# PR-07 — Observability (local/dev)

This document describes the lightweight observability layer for the InvForge AI
Operations sidecar: a health endpoint, a Prometheus-compatible `/metrics`
endpoint, structured logging, and an optional local Prometheus + Grafana stack.

> **Limitation — local/dev only.** Everything here is for local development and
> demos. This is **not** production monitoring. There is no alerting, no
> long-term storage, no HA, no remote write, and no SLO tooling. No production
> monitoring claims are made.

## Components

| Path | Purpose |
|------|---------|
| `observability/health.py` | Builds the `/health` status payload from safe artifact summary fields. |
| `observability/metrics.py` | Defines and renders the Prometheus metrics. |
| `observability/logging.py` | Structured JSON logging for observability events. |
| `observability/smoke.py` | Offline smoke test (no Docker, no server). |
| `observability/prometheus/prometheus.yml` | Local Prometheus scrape config. |
| `observability/grafana/provisioning/` | Auto-provisioned Grafana datasource + dashboard. |
| `observability/docker-compose.observability.yml` | Independent local Prometheus + Grafana stack. |

The health and metrics modules read **only** artifact existence, mtime, and a
small set of allowlisted scalar summary fields (drift status, champion/
challenger decision, BentoML packaging status). They never read raw artifact
payloads, never expose file paths, secrets, PII, or high-cardinality values.

## 1. Start the AI Operations API

The API exposes `/health` and `/metrics` (plus the pre-existing PR-02 routes).

```bash
make UV="uv" observability-api
# equivalent to:
# uv run --group observability uvicorn api.main:app --host 0.0.0.0 --port 8001
```

Local URL: `http://localhost:8001` (override the port with `INVFORGE_API_PORT`).

> The API imports cleanly even without the `observability` group installed; in
> that case `/health` still works and `/metrics` returns HTTP 503 explaining the
> optional group is required.

## 2. Access `/health`

```bash
curl http://localhost:8001/health
```

Expected response shape (HTTP 200 when `ok`/`degraded`, HTTP 503 when
`unavailable`):

```json
{
  "status": "ok",
  "pr_stage": "PR-07",
  "artifacts": {
    "decision_summary": "ok",
    "decision_recommendations": "ok",
    "mlops_loop_summary": "ok",
    "registry_summary": "ok",
    "champion_challenger_comparison": "ok"
  },
  "drift_detected": false,
  "bentoml_packaged": false,
  "champion_challenger_decision": "manual_review"
}
```

- `status` is `unavailable` when no artifacts are present, `degraded` when some
  are present, and `ok` when all are present.
- `drift_detected` is `true`/`false`/`null` (`null` = unknown).
- `bentoml_packaged` is `true`/`false`/`null`.
- `champion_challenger_decision` is one of `promote_challenger`,
  `keep_champion`, `manual_review`, `no_comparison`, `unknown`.

Generate artifacts first (so health reports `ok`):

```bash
make UV="uv" generate-data
make UV="uv" train-ml
make UV="uv" decision-intel
make UV="uv" mlops-loop
```

## 3. Access `/metrics`

```bash
curl http://localhost:8001/metrics
```

Returns the Prometheus text exposition format, including:

```
invforge_service_info{version="0.2.0",pr_stage="PR-07"} 1.0
invforge_artifact_available{artifact="decision_summary"} 1.0
invforge_artifact_age_seconds{artifact="decision_summary"} 123.0
invforge_drift_detected 0.0
invforge_champion_challenger_decision{decision="manual_review"} 1.0
invforge_bentoml_packaged 0.0
invforge_api_requests_total{method="GET",endpoint="/health",status_code="200"} 1.0
invforge_api_request_duration_seconds_bucket{method="GET",endpoint="/health",le="0.1"} 1.0
```

## 4. Start Prometheus + Grafana locally (optional, Docker)

The observability stack is **fully independent** of the InvenTree Docker
compose. It does not extend, include, share volumes with, or modify any
InvenTree service. It creates its own bridge network `invforge-observability`.

```bash
# Start the API first (separate terminal):
make UV="uv" observability-api

# Then bring up Prometheus + Grafana:
make UV="uv" observability-up

# Tear down:
make UV="uv" observability-down
```

Prometheus scrapes **only** the AI Operations API at `host.docker.internal:8001`
(`/metrics`). On Docker Desktop (macOS/Windows) this resolves automatically; on
Linux the compose file maps `host.docker.internal` to the host gateway. It does
**not** scrape InvenTree or anything else.

## 5. Open Grafana

- URL: `http://localhost:3000`
- Default credentials: `admin` / `admin` — **local-only dev credentials, not
  for production**. Anonymous viewer access is also enabled for convenience.

The dashboard **InvForge AI Operations — Observability (local/dev)** is
auto-provisioned (folder *InvForge*) and loads on first startup — no manual
import needed. Prometheus URL: `http://localhost:9090`.

## 6. Metric reference

Each metric below is exactly what the API exposes (low-cardinality, safe).
`-1` always means "value could not be determined safely" (unknown).

| Metric | Type | Meaning |
|--------|------|---------|
| `invforge_service_info{version,pr_stage}` | Gauge | Constant `1`; carries service version and PR stage. |
| `invforge_artifact_available{artifact}` | Gauge | `1` if the artifact exists, `0` if missing. `artifact` is a fixed key, never a filename/path. |
| `invforge_artifact_age_seconds{artifact}` | Gauge | Seconds since the artifact's mtime; `-1` if missing/unknown. |
| `invforge_drift_detected` | Gauge | `1` drift detected, `0` no drift, `-1` unknown. |
| `invforge_champion_challenger_decision{decision}` | Gauge | One-hot: active decision `= 1`, others `= 0`. `decision` ∈ {promote_challenger, keep_champion, manual_review, no_comparison, unknown}. |
| `invforge_bentoml_packaged` | Gauge | `1` if champion model packaged to the local BentoML store, else `0`. |
| `invforge_api_requests_total{method,endpoint,status_code}` | Counter | API request count by method, normalized endpoint, and status code. |
| `invforge_api_request_duration_seconds{method,endpoint}` | Histogram | API request latency by method and normalized endpoint. |

Allowed `artifact` label values: `decision_summary`,
`decision_recommendations`, `mlops_loop_summary`, `registry_summary`,
`champion_challenger_comparison`. Endpoints not on the known allowlist are
normalized to `other` to keep cardinality bounded.

## 7. Structured logging

Observability events are emitted as structured JSON lines with at least:

```json
{"timestamp": "2026-06-02T23:59:00+00:00", "level": "info",
 "event": "health_status_built", "component": "health",
 "artifact": null, "status": "ok"}
```

Logs never contain file contents, absolute paths, model weights, predictions,
secrets, full dataframes, or stack traces (an optional `error` key carries a
short message only).

## 8. Smoke test

```bash
make UV="uv" observability-smoke
```

Runs offline in well under 10 seconds (no Docker, no server, no browser). It
verifies the health builder degrades safely on missing paths, returns the full
contract on real paths, all metrics are registered by name, and no metric label
value contains a path separator. Exits non-zero on any failure.

## 9. Intentionally deferred (out of scope for PR-07)

- **Loki, Tempo, Mimir, AlertManager / full LGTM stack** → PR-11 (Senior Edition)
- **Cloud / production monitoring** → PR-10 and beyond
- **Kubernetes observability** → PR-11
- **Complex alerting rules** → PR-11
- **Deep Evidently data-quality parsing** → future improvement; PR-07 exposes
  only a simple drift status plus artifact availability/age.

## 10. Limitations

- This is **local/dev observability only**. It makes **no production monitoring
  claims**.
- All underlying data is synthetic (seed 42); metrics reflect synthetic
  pipeline state, not live InvenTree demand.
- Prometheus retention is short (local TSDB) and Grafana credentials are
  local-only dev defaults.
