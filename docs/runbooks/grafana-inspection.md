# Runbook — Grafana inspection (PR-11B)

How to verify Grafana provisioning (datasources + dashboard) and read each panel
against the real signals.

## Open Grafana

```bash
make obs-k8s-port-forward     # if not already running
open http://localhost:3000    # admin/admin or anonymous Viewer
```

## Verify datasource provisioning

Configuration → Data sources. You should see four provisioned datasources:

| Name | Type | URL | Status |
|------|------|-----|--------|
| Prometheus (default) | prometheus | http://prometheus:9090 | working |
| Loki | loki | http://loki:3100 | working |
| Tempo | tempo | http://tempo:3200 | working (idle backend) |
| Alertmanager | alertmanager | http://alertmanager:9093 | working |

"Save & test" each. They are provisioned from `grafana-datasources` (ConfigMap),
so they appear automatically — no manual setup.

## The dashboard

Dashboards → InvForge → "InvForge AI Operations — Observability (kind/PR-11B)".

| Panel | Source | Query (real) |
|-------|--------|--------------|
| AI API up | Prometheus | `up{job="invforge-ai"}` |
| Drift detected | Prometheus | `invforge_drift_detected` |
| BentoML packaged | Prometheus | `invforge_bentoml_packaged` |
| Artifact availability | Prometheus | `invforge_artifact_available` |
| API request rate by status | Prometheus | `sum by (status_code) (rate(invforge_api_requests_total[5m]))` |
| API p95 latency | Prometheus | `histogram_quantile(0.95, ... invforge_api_request_duration_seconds_bucket ...)` |
| Firing alerts | Prometheus | `ALERTS{alertstate="firing"}` |
| AI layer logs | Loki | `{namespace="invforge-ai"}` |
| Traces (Tempo) | — | text panel: "pending API instrumentation" |

Every metric panel uses the verified PR-07 metric contract
(`observability/metrics.py`). No invented metrics.

## Generate some data

To make the request-rate / latency panels move, hit the AI API a few times via
its port-forward (separate terminal):

```bash
kubectl -n invforge-ai port-forward svc/invforge-ai-api 8001:8001
for i in $(seq 1 20); do curl -s localhost:8001/health >/dev/null; curl -s localhost:8001/v1/data/summary >/dev/null; done
```

## Logs panel

The Loki panel shows the AI API's structured JSON logs collected by Promtail.
Try a LogQL filter, e.g. `{namespace="invforge-ai"} |= "api_startup"`.
