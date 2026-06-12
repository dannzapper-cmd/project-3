# ADR 003 — Advanced observability + data lineage scope (PR-11B)

- **Status:** Accepted
- **Date:** 2026-06-03
- **Context PR:** PR-11B — Advanced Observability + Data Lineage
- **Extends:** ADR 002 (PR-11A Kubernetes scope)

## Context

PR-11A built the Kubernetes spine for the AI Operations Layer (kind + Helm, AI
API Deployment/Service, probes, limits, NetworkPolicy, retraining templates).
PR-11B adds the "nervous system": logs, metrics, traces, alerts, and optional
data lineage — for the AI layer only, with strict RAM discipline, no cloud
resources, no secrets, and no InvenTree core changes.

## Decision

### PR-11B is a separate PR from PR-11A

PR-11A is the spine; PR-11B is the telemetry. Keeping them separate keeps each
reviewable and lets the baseline cluster (`make k8s-up`/`k8s-smoke`) stay small
and fast. Nothing in PR-11B is required for PR-11A to work.

### Observability is an OPTIONAL profile, never default

The stack installs via `make obs-k8s-up` into its own namespace
(`invforge-observability`) and is **never** started by `make k8s-up`. This
protects the 8 GB budget: you run the baseline AI cluster by default and only add
~2 GB of observability when you want it. (Note: PR-07 already owns the
`observability-*` Make targets for a host Docker-Compose Prometheus+Grafana
stack; PR-11B uses the distinct `obs-k8s-*` prefix so both coexist and neither is
broken.)

### One self-contained chart, lightweight components

A single chart (`deploy/k8s/observability`) ships Prometheus, Grafana, Loki
(single-binary), Promtail, Tempo (single-binary), AlertManager, an OTel
Collector, and a local webhook receiver — as plain Deployments/ConfigMaps with
explicit per-component requests/limits and ephemeral (emptyDir) storage. We chose
this over umbrella dependencies on `loki-stack`/`kube-prometheus-stack` because:

- it is **offline-validatable** here (helm lint/template + kubeconform) with no
  external chart-repo pulls;
- it gives **exact, auditable RAM limits per component** (the addendum's table);
- it avoids **CRD sprawl** and the **duplicate-Grafana** conflict that umbrella
  charts introduce;
- single-binary Loki/Tempo are the right size for one kind node.

This is the deliberate adaptation of the suggested `loki-stack` path; the log
collection is still real (Promtail DaemonSet with Kubernetes service discovery).

### Truth about each signal

- **Metrics — REAL.** Prometheus scrapes the AI API `/metrics`
  (`job=invforge-ai`) via in-cluster DNS. The Grafana dashboard uses ONLY the
  verified PR-07 metric contract (`observability/metrics.py`):
  `up`, `invforge_drift_detected`, `invforge_artifact_available`,
  `invforge_bentoml_packaged`, `invforge_api_requests_total`,
  `invforge_api_request_duration_seconds`. No invented metrics.
- **Logs — REAL.** Promtail (DaemonSet) discovers pods via the Kubernetes API
  and tails their stdout from the node, pushing to Loki. The AI API already
  emits structured JSON logs (PR-07 `observability/logging.py`). Grafana has a
  Loki datasource + a logs panel scoped to `namespace="invforge-ai"`.
- **Alerts — REAL.** Three Prometheus rules on real metrics:
  1. `up{job="invforge-ai"} == 0` for 1m → **InvForgeAIDown** (critical);
  2. `invforge_drift_detected == 1` for ~2 evaluations → **InvForgeDriftDetected**;
  3. `invforge_artifact_available{artifact="decision_summary"} == 0` for 5m →
     **InvForgeArtifactMissing**.
  AlertManager routes to an in-cluster **webhook receiver** (a tiny stdlib Python
  server) that logs the alert to stdout, closing the loop
  metric → rule → alert → receiver → `kubectl logs`. No external service, no
  null receiver, no secrets. `obs-k8s-alert-test` exercises rule #1 end to end.
- **Traces — PENDING (honest).** Tempo and the OTel Collector are deployed as
  OTLP receivers (`tempo:3200`, `otel-collector:4317/4318`) and run idle, ready
  to receive. The AI API is **not OTEL-instrumented**, so no traces flow yet. We
  deliberately did **not** instrument the API (that is invasive app work, out of
  PR-11B scope). The Grafana Tempo panel says "Traces pending API
  instrumentation". Enabling traces = adding `opentelemetry-fastapi` +
  `opentelemetry-sdk` to the API and pointing `OTEL_EXPORTER_OTLP_ENDPOINT` at
  the collector — deferred (see `docs/runbooks/otel-tracing.md`).

### Data lineage — emission implemented + validated; Marquez deployment provided

`mlops/retraining/lineage.py` is a small, **env-gated** OpenLineage wrapper. With
`OPENLINEAGE_URL` unset it is a complete no-op (the default `make retrain-smoke`
and CI are unchanged). With it set, `run_retraining` emits real OpenLineage
`START`/`COMPLETE`/`FAIL` run events for the `invforge.retraining` job. This is
~15 lines of wrapper around the existing pipeline entrypoint — not a refactor,
and it does not go through any ZenML server (the pipeline is local/offline).
Event emission is **validated by a unit test** (`ml/tests/test_retraining_lineage.py`)
that captures real `RunEvent` objects via a recording client. A Marquez profile
(`deploy/k8s/lineage`, namespace `invforge-lineage`, API + web + ephemeral
embedded PostgreSQL) and `make lineage-*` targets are provided. End-to-end Marquez
UI inspection requires Docker/kind and is the local step in
`docs/runbooks/lineage-inspection.md` (`make lineage-smoke` emits one real event
and queries Marquez for the job).

### Why Mimir is excluded

Single-binary Prometheus already covers local metric storage at this scale.
Mimir is a horizontally-scalable, multi-tenant metrics backend — pure overhead
and RAM cost for one kind node. Excluded.

### Why OpenMetadata is excluded

OpenMetadata is a heavy metadata platform (its own DB, search, ingestion
framework). Marquez alone covers the OpenLineage demo cleanly. Excluded.

### Why no cloud observability

Grafana Cloud / Datadog / managed Prometheus all require accounts, credentials,
and standing cost, and would violate the no-cloud / no-secrets rules. Everything
here runs locally on kind at $0.

## RAM / cost trade-offs

Per-component requests/limits are set explicitly (see `values.yaml`). Budget:
observability requests ~0.85 GiB / limits ~2.0 GiB; lineage requests ~0.5 GiB /
limits ~1.5 GiB. Run **one heavy profile at a time** and stop InvenTree Compose
first. The baseline AI cluster stays untouched by default.

## What is implemented vs deferred

| Item | Status |
|------|--------|
| Prometheus scraping AI API + 3 real alert rules | Implemented |
| Grafana + datasources (Prometheus/Loki/Tempo/Alertmanager) + real dashboard | Implemented |
| Loki + Promtail real pod-log collection | Implemented |
| AlertManager → in-cluster webhook receiver (loop closed) | Implemented |
| Tempo + OTel Collector (OTLP backends) | Deployed, idle (no traces yet) |
| API OTEL instrumentation (traces source) | Deferred |
| OpenLineage emission from retraining (env-gated) | Implemented + unit-validated |
| Marquez deployment + lineage targets | Implemented (E2E UI = local step) |
| Mimir, OpenMetadata, cloud observability, Redis | Excluded / deferred |

## Consequences

- InvForge gains a real, optional, auditable observability + lineage layer for the
  AI workloads without touching the baseline cluster, InvenTree, or the cloud.
- Every claim is backed by a config, a test, or an explicit defer note.
