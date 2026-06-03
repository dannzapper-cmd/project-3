# InvForge — Advanced Observability (PR-11B)

A single, self-contained, 8 GB-friendly Helm chart that adds logs, metrics,
traces (backend), and alerts for the InvForge **AI Operations Layer only**. It is
an **optional profile**: it is never started by `make k8s-up`. InvenTree is never
deployed here. No cloud resources, no secrets.

## Components (all ClusterIP, ephemeral storage, explicit resource limits)

| Component | Role | Status |
|-----------|------|--------|
| Prometheus | scrapes AI API `/metrics` (job=invforge-ai), evaluates alert rules | **Real** |
| Grafana | dashboards + datasources (Prometheus, Loki, Tempo, Alertmanager) | **Real** |
| Loki (single-binary) | log store | **Real** |
| Promtail (DaemonSet) | ships pod stdout (AI API JSON logs) to Loki | **Real** |
| AlertManager | routes 3 real alert rules to the webhook receiver | **Real** |
| alert-webhook-receiver | in-cluster Python server; logs alerts to stdout | **Real** |
| Tempo (single-binary) | OTLP trace backend, ready to receive | **Backend only** |
| OTel Collector | OTLP receiver → Tempo | **Backend only** |

Traces are **pending**: the AI API is not OTEL-instrumented, so no traces flow
yet (deferred — see `docs/runbooks/otel-tracing.md` and ADR 003). This is stated
honestly in the Grafana Tempo panel.

## Quick start

```bash
# Prereq: AI layer running (PR-11A), InvenTree Compose stopped (8 GB RAM).
make k8s-up && make k8s-deploy            # PR-11A baseline (if not already up)

make obs-k8s-up                            # install this chart
make obs-k8s-status                        # pods/services
make obs-k8s-port-forward                  # port-forward grafana/prom/loki/tempo/alertmanager
make obs-k8s-smoke                         # health checks + real-metric probe
# Grafana: http://localhost:3000  (admin/admin or anonymous viewer)
make obs-k8s-down                          # uninstall
```

Alert loop test (real condition):

```bash
bash deploy/k8s/observability/scripts/alert-test.sh   # scales AI API to 0 -> alert -> webhook log
```

## RAM budget

Requests ~0.85 GiB, limits ~2.0 GiB total (per-component values in
`values.yaml`). Designed to run with the AI API on an 8 GB laptop **without**
InvenTree Compose. See `docs/runbooks/observability-startup.md` and ADR 003.

## Layout

```
deploy/k8s/observability/
  Chart.yaml  values.yaml
  dashboards/invforge-ai.json
  templates/  (prometheus, grafana, loki, promtail, tempo, alertmanager,
               otel-collector, webhook-receiver, namespace, NOTES.txt)
  scripts/    (port-forward.sh, stop-forward.sh, smoke.sh, alert-test.sh)
```
