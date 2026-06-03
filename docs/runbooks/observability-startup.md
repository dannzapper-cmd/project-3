# Runbook — Advanced observability startup (PR-11B)

Bring up the **optional** observability stack (Prometheus, Grafana, Loki,
Promtail, Tempo, AlertManager, OTel Collector, webhook receiver) for the AI
layer on local kind. It is never started by `make k8s-up`. InvenTree is never
deployed here. No cloud, no secrets.

## Prerequisites

Same tools as PR-11A: Docker, kind ≥ 0.23, kubectl ≥ 1.29, helm ≥ 3.14.

**RAM:** the observability stack targets ~2 GB (requests ~0.85 GiB, limits
~2.0 GiB) and the AI API ~1 GB → ~3 GB minimum free. 8 GB total is enough
**without** InvenTree Compose running. Run one heavy thing at a time:

```bash
make docker-down     # stop InvenTree Compose if running
```

## Mandatory sequence

```bash
# 1) Baseline AI cluster (PR-11A) — skip if already up.
make docker-build-ai
make k8s-up
make k8s-deploy
make k8s-smoke        # confirm AI API /health + /metrics

# 2) Observability profile (this PR).
make obs-k8s-up                # helm upgrade --install into invforge-observability
make obs-k8s-status            # wait until all pods are Running (no CrashLoopBackOff)

# 3) Port-forward, then smoke.
make obs-k8s-port-forward      # grafana/prom/loki/tempo/alertmanager -> localhost
make obs-k8s-smoke             # health checks + real-metric probe

# 4) Tear down when done.
make obs-k8s-down
```

## Required port-forwards (what obs-k8s-port-forward does)

```bash
kubectl -n invforge-observability port-forward svc/grafana 3000:3000
kubectl -n invforge-observability port-forward svc/prometheus 9090:9090
kubectl -n invforge-observability port-forward svc/loki 3100:3100
kubectl -n invforge-observability port-forward svc/tempo 3200:3200
kubectl -n invforge-observability port-forward svc/alertmanager 9093:9093
```

## obs-k8s-smoke sequence (what it verifies)

1. `GET http://localhost:9090/-/healthy` → Prometheus healthy
2. `GET http://localhost:3000/api/health` → Grafana UI
3. `GET http://localhost:3100/ready` → Loki ready
4. `GET http://localhost:3200/ready` → Tempo ready (idle backend)
5. `GET http://localhost:9093/-/healthy` → AlertManager healthy
6. `GET http://localhost:9090/api/v1/query?query=invforge_drift_detected` → a
   REAL InvForge metric is present (proves the AI API scrape works)

The target exits non-zero on the first failure with a clear message.

## Access

- Grafana: http://localhost:3000 — admin/admin (or anonymous Viewer). Dashboard:
  "InvForge AI Operations — Observability (kind/PR-11B)".
- Prometheus: http://localhost:9090 (see `/alerts`, `/targets`).
- AlertManager: http://localhost:9093.

## NetworkPolicy note

PR-11A ships structural NetworkPolicy in `invforge-ai`. kindnet does not enforce
it, so cross-namespace scraping (observability → AI API) works on default kind.
If you switch to Calico (real enforcement), add an ingress rule allowing the
`invforge-observability` namespace to reach the AI API on 8001.

## Truthful status

Metrics, logs, and alerts are real and validated by the smoke. Traces are
**pending API instrumentation** (Tempo/OTel are deployed as idle receivers) —
see `docs/runbooks/otel-tracing.md`.

## Troubleshooting

- **Pod Pending / OOM**: not enough free RAM. `make docker-down`, and consider
  `make obs-k8s-down` for the lineage profile if it is also running.
- **Grafana panels empty**: give Prometheus one scrape interval; confirm the AI
  API is deployed (`make k8s-deploy`) and `/targets` shows `invforge-ai` UP.
- **CrashLoopBackOff**: `kubectl -n invforge-observability logs deploy/<name>`.
