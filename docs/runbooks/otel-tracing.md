# Runbook — OpenTelemetry tracing (PR-11B): status and how to enable

## Current status: traces are PENDING (honest)

PR-11B deploys the **trace backends** but the AI API does **not** emit traces
yet, so there is nothing to display. This is deliberate and stated in the Grafana
Tempo panel.

What IS deployed and ready to receive:

- **Tempo** (single-binary) — OTLP backend, query API at `tempo:3200`, OTLP
  receivers at `tempo:4317` (gRPC) / `tempo:4318` (HTTP). Grafana has a Tempo
  datasource. It runs idle.
- **OTel Collector** (Deployment) — OTLP receiver at `otel-collector:4317`
  (gRPC) / `otel-collector:4318` (HTTP), exporting traces to `tempo:4317`. It
  does **not** scrape Prometheus (no duplication). Idle until something sends it
  spans.

Data flow once active:

```
AI API (OTLP) ──▶ otel-collector:4317 ──▶ tempo:4317 ──▶ Grafana (Tempo DS)
```

## Why the API is not instrumented in PR-11B

Instrumenting the API means adding `opentelemetry-sdk` +
`opentelemetry-instrumentation-fastapi` and changing `api/` startup code. That is
invasive application work and explicitly **out of PR-11B scope** (PR-11B is
env/config/chart only). We did not fake traces.

## How to enable traces later (deferred task)

1. Add to the API dependency surface (a new optional group, e.g. `tracing`):
   - `opentelemetry-sdk`
   - `opentelemetry-exporter-otlp`
   - `opentelemetry-instrumentation-fastapi`
2. In the API startup, instrument the FastAPI app and configure the OTLP
   exporter from env, e.g.:
   - `OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317`
   - `OTEL_SERVICE_NAME=invforge-ai-ops-api`
3. Add those env vars to the AI API ConfigMap (PR-11A chart) — no Secret needed.
4. Redeploy the API, generate some requests, then open Grafana → Explore →
   Tempo and search by service `invforge-ai-ops-api`.

No change to the observability chart is required to receive the traces — the
collector and Tempo are already wired. This keeps the future change small.
