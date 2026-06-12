# Backend and ML explainer — InvForge for reviewers

This document explains how InvForge fits together in practical terms. It is
technical, honest, and aimed at someone evaluating the project locally.

## Sidecar architecture

InvForge never patches InvenTree. The base inventory system runs unchanged in
`app/docker-compose.yml` (official `inventree/inventree` images). InvForge adds
external services that **could** read from InvenTree's REST API but default to
**synthetic data** for reproducible demos.

```
InvenTree (Docker Compose)     InvForge sidecar (uv / Docker / kind)
  PostgreSQL, Redis, worker  →   FastAPI, ML, MLOps, dashboard
```

Kubernetes work deploys **only the AI Operations Layer** (`deploy/k8s/helm/invforge`).
Observability and lineage are **optional local profiles** in separate namespaces.

## What InvenTree does

InvenTree is the open-source inventory management system: parts, stock, BOMs,
suppliers, and workflows. InvForge treats it as the system of record for real
deployments. In the default demo path, InvForge does not require InvenTree to be
running.

## What InvForge adds

| Layer | Role |
|-------|------|
| **API** (`api/`) | FastAPI sidecar: health, metrics, read-only status, gated ingestion |
| **Synthetic data** (`data/synthetic/`) | Deterministic CSV generator (seed 42) |
| **ML** (`ml/`) | Demand forecasting baselines (LightGBM, StatsForecast, Croston/SBA) |
| **Decision intelligence** (`ml/decision_intelligence.py`) | Safety stock, ROP, EOQ, stockout risk from forecasts |
| **MLOps** (`mlops/`) | MLflow tracking, Evidently reports, champion/challenger, BentoML packaging |
| **Retraining** (`mlops/retraining/`) | ZenML local DAG, Optuna smoke, gated promotion, rollback |
| **Dashboard** (`dashboard/`) | Streamlit read-only visualization of artifacts |
| **Observability** (`observability/`) | `/health`, `/metrics`, local Prometheus/Grafana, optional k8s LGTM stack |
| **Security** (`security/`) | Audit pipeline, risk scoring, secrets scanning hooks |
| **Deploy** (`deploy/`) | Docker image, GCP/AWS/Azure templates, kind Helm charts |

## API role

The FastAPI app (`api/main.py`) is the **control-plane surface** for operators:

- `GET /health` — artifact presence, drift flag, champion/challenger decision
- `GET /metrics` — Prometheus metrics (optional dependency group)
- `GET /v1/inventory/status` — config + local data summary (no token leakage)
- `GET /v1/data/summary` — read-only processed data summary
- `POST /v1/ingest/inventree` — **mutation**; blocked when `INVFORGE_ALLOW_MUTATIONS=false`

In **demo/cloud mode** (`INVFORGE_ENV=demo`), `/health` returns HTTP 200 even
without local artifacts so container probes succeed; the JSON still reports truthfully.

## Synthetic data role

`make generate-data` writes CSVs to `data/synthetic/output/` (gitignored). This
keeps CI and reviewer machines reproducible without private inventory data.
`make validate-data` runs Pandera schemas on synthetic and processed paths.

## ML pipeline role

`make train-ml` trains baseline forecasters and logs to local MLflow (`mlruns/`).
Models support regular and intermittent demand SKUs. Outputs feed decision
intelligence and the MLOps loop.

**Forecast quantiles (p10 / p50 / p90):** demand forecasts include pessimistic,
median, and optimistic quantiles. Decision intelligence uses these — not just a
single point forecast — when estimating safety stock and stockout risk.

**Stockout risk:** a simulated diagnostic ranking SKUs where forecast uncertainty,
lead time, and on-hand inventory suggest elevated shortage probability. It is a
**backtest-style signal** for the dashboard, not a live InvenTree alert.

## Decision intelligence role

`make decision-intel` turns forecasts into inventory policy recommendations:
safety stock, reorder points, EOQ, and stockout risk scores. Results land in
`artifacts/decision/`. These are **simulated backtest diagnostics** — not claims
of real-world savings.

## MLOps loop role

`make mlops-loop` runs Evidently drift/quality checks, updates registry metadata,
compares champion vs challenger, and packages a minimal BentoML bundle. Summary
JSON drives dashboard section 4 and `/health` drift fields.

| Tool | Role |
|------|------|
| **MLflow** | Experiment tracking and model registry metadata (`mlruns/`) |
| **Evidently** | Data drift and quality JSON reports under `artifacts/mlops/evidently/` |
| **ZenML** | Retraining DAG orchestration (PR-09; local SQLite stack) |
| **BentoML** | Model packaging summary; optional containerized serving on kind |

## Dashboard role

`make dashboard` launches Streamlit. Each panel loads **existing artifacts only**
— it does not retrain or mutate data. See `docs/dashboard.md` for panel meanings.

| Panel | What it answers |
|-------|-----------------|
| Overview | Are data / ML / decision / MLOps artifacts present? |
| Forecast performance | Which model won champion/challenger? |
| Decision intelligence | Top reorder recommendations and risk |
| MLOps status | Drift detected? Registry strategy? Bento packaged? |
| Limitations | Synthetic disclaimer and deferred scope |

## Observability role

PR-07 adds API `/metrics` and a small local Prometheus/Grafana compose stack
(`make observability-up`). PR-11B adds an **optional** kind profile
(`make obs-k8s-up`) with Prometheus, Grafana, Loki, Tempo, and Alertmanager in
namespace `invforge-observability`. Tempo/OTel are deployed but idle until future
API tracing instrumentation.

## Security layer role

`make security-audit` generates defensive artifacts under `artifacts/security/`.
`make secrets-scan` and `make security-check` run detect-secrets, Bandit, and
pip-audit. Mutation endpoints are blocked in demo/cloud deploy modes.

## Kubernetes profile role

PR-11A (`make k8s-up`, `make k8s-deploy`) runs the AI API on a local kind
cluster. BentoML serving, retraining Jobs, and blue/green switches are
**templated but opt-in** — they require built images (`make bento-build`, etc.).

## Cloud deployment profile role

| Profile | Status |
|---------|--------|
| **GCP Cloud Run** | Primary documented target; template + example scripts |
| **AWS ECS/Fargate** | Reproducibility template; manual activation |
| **Azure Container Apps** | Reproducibility template; manual activation |

Only the **AI Operations API container** is in scope for cloud profiles.
InvenTree, MLflow, ZenML, Streamlit, and retraining remain **local-only**
unless a future production architecture is defined. See `docs/deployment-contract.md`.

## What remains local-only

- InvenTree Docker Compose stack
- Streamlit dashboard
- MLflow / ZenML / full retraining loop
- Marquez lineage UI (optional kind profile)
- Training and artifact generation

## What is deployable publicly

The slim `Dockerfile` image exposing read-only endpoints is designed for Cloud Run
or equivalent container hosts. Use placeholders, Secret Manager, billing warnings,
and `teardown.example.sh` scripts — never claim production deployment from
templates alone.

## Why mutation endpoints are blocked in demo/cloud mode

`POST /v1/ingest/inventree` writes snapshots and calls InvenTree. On a public
demo surface that is unsafe. `INVFORGE_ALLOW_MUTATIONS=false` (default in cloud
templates) returns HTTP 403. Local trusted use can enable mutations explicitly.

## Artifacts map

| Path | Generator |
|------|-----------|
| `data/synthetic/output/*.csv` | `make generate-data` |
| `mlruns/` | `make train-ml`, MLOps, retraining |
| `artifacts/decision/` | `make decision-intel` |
| `artifacts/mlops/` | `make mlops-loop` |
| `artifacts/retraining/` | `make retrain-smoke` |
| `artifacts/security/` | `make security-audit` |

## OpenLineage / lineage

When `OPENLINEAGE_URL` is set (e.g. Marquez port-forward on `:5000`),
`make retrain-smoke` emits a real OpenLineage event. `make lineage-smoke` verifies
Marquez recorded job `invforge.retraining`. Emission is a no-op when the URL is unset.

## Further reading

- [Quick demo walkthrough](quick-demo-walkthrough.md)
- [Demo scenario](../../examples/demo-scenario/README.md)
- `PROJECT_3_INVFORGE_MASTER_CONTEXT.md`
- `docs/deployment-contract.md`
