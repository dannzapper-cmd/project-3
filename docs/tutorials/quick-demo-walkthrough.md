# Quick demo walkthrough — InvForge from zero

This guide helps a reviewer run InvForge locally, try the live cloud demo, and
know which claims are safe to make. All commands come from the repo `Makefile` —
run `make help` for the full list.

## 5 minutes — browser only (live cloud)

1. Open live dashboard: https://invforge-dashboard-demo-lwcelvo7ya-uc.a.run.app
   - Sign in: `reviewer` / `invforge-demo`
   - Note the read-only banner
2. Open live API docs: https://invforge-ai-demo-lwcelvo7ya-uc.a.run.app/docs
3. Execute `GET /health` — expect HTTP 200
4. Execute `GET /v1/inventory/status` — read-only config summary
5. Confirm `POST /v1/ingest/inventree` is blocked (403) in cloud mode

## 15 minutes — local dashboard

```bash
uv sync --group dev --group pipeline --group ml --group mlops --group dashboard --group observability
cp app/.env.example app/.env
make reviewer-demo
make dashboard
```

Open http://localhost:8501 and walk through sections 0–4.

## 30 minutes — local + API + samples

After the 15-minute path:

```bash
make observability-api   # terminal 2
curl http://localhost:8001/health
curl http://localhost:8001/metrics
```

Review sample inputs:

- `examples/demo-scenario/scenario.yaml`
- `examples/api/forecast_request.json`

Full guide: [`REVIEWER_DEMO_GUIDE.md`](../REVIEWER_DEMO_GUIDE.md)

---

## What InvForge is

InvForge is an **external AI Operations sidecar** over [InvenTree](https://inventree.org/).
It adds demand forecasting, decision intelligence, MLOps, observability, and
defensive security **without modifying InvenTree core**. InvenTree stays in
Docker Compose; the AI layer is a separate FastAPI service and local tooling.

## What you will see

After the local pipeline runs you get:

- Synthetic inventory CSVs under `data/synthetic/output/` (regenerated, not committed)
- MLflow runs under `mlruns/` (local, gitignored)
- Decision and MLOps artifacts under `artifacts/`
- A Streamlit dashboard (`make dashboard`) visualizing those artifacts
- A FastAPI service with `/health`, `/metrics`, and read-only inventory endpoints

Everything uses **deterministic synthetic data** (seed 42) unless you explicitly
ingest from a live InvenTree instance.

## Prerequisites

- Docker and Docker Compose v2 (for InvenTree base stack and optional Docker smoke)
- [uv](https://docs.astral.sh/uv/) (Python 3.12+)
- `make`
- Optional for Kubernetes profiles: `kind`, `kubectl`, `helm`

Install Python dependencies:

```bash
uv sync --group dev --group pipeline --group ml --group mlops --group dashboard --group observability
```

## Setup

```bash
cp app/.env.example app/.env
```

InvenTree is pinned via `INVENTREE_TAG` in `app/.env.example` (v1.3.2).

Optional — start the InvenTree base stack (not required for the synthetic-data demo):

```bash
make docker-up
make docker-init   # first time only
```

## Fast local demo (no long-running servers)

Chain the core offline pipeline:

```bash
make reviewer-demo   # or: make demo-local
```

This runs: `generate-data` → `validate-data` → `train-ml` → `decision-intel` →
`mlops-loop` → `dashboard-smoke`. It does **not** start Docker, Kubernetes, or
the Streamlit server.

## Step-by-step (manual)

### 1. Generate synthetic data

```bash
make generate-data
```

### 2. Validate data

```bash
make validate-data
```

### 3. Train ML baseline

```bash
make train-ml
```

### 4. Decision intelligence

```bash
make decision-intel
```

### 5. MLOps loop

```bash
make mlops-loop
```

### 6. Dashboard (interactive)

```bash
make dashboard
```

Open the URL Streamlit prints (typically `http://localhost:8501`).

Non-interactive check:

```bash
make dashboard-smoke
```

### 7. API + observability endpoints

In a separate terminal:

```bash
make observability-api
```

Then:

```bash
make api-health
curl -s http://localhost:8001/health | jq .
curl -s http://localhost:8001/metrics | head
curl -s http://localhost:8001/v1/inventory/status | jq .
```

### 8. Optional retraining smoke

```bash
make retrain-smoke
make retraining-check
```

## Optional Docker smoke (AI Operations container)

Builds the deployable image, runs it in demo mode, smoke-tests, tears down:

```bash
make docker-smoke
make dashboard-docker-smoke
```

## Optional kind smoke (local Kubernetes AI layer)

**8 GB Mac:** stop InvenTree Compose first (`make docker-down`). Run stacks one at a time.

```bash
make docker-build-ai
make k8s-preflight
make k8s-up
make k8s-deploy
make k8s-status
make k8s-smoke
make k8s-down
```

## Optional observability profile (PR-11B)

Requires a running kind cluster **with the AI layer deployed**. See
`docs/runbooks/observability-startup.md`.

```bash
make k8s-up && make k8s-deploy
make obs-k8s-up
make obs-k8s-port-forward
make obs-k8s-smoke
make obs-k8s-down
make k8s-down
```

## Optional lineage profile (PR-11B)

```bash
make lineage-up
make lineage-port-forward
make lineage-smoke
make lineage-down
```

## Local vs live cloud surfaces

| Surface | Where it runs | Command / URL |
|---------|---------------|---------------|
| Streamlit dashboard (full pipeline) | **Local** | `make dashboard` → http://localhost:8501 |
| Streamlit dashboard (fixtures) | **Live Cloud Run** | https://invforge-dashboard-demo-lwcelvo7ya-uc.a.run.app (`reviewer` / `invforge-demo`) |
| FastAPI (full artifacts) | **Local** | `make observability-api` → http://localhost:8001 |
| FastAPI (read-only demo) | **Live Cloud Run** | https://invforge-ai-demo-lwcelvo7ya-uc.a.run.app |

The live Cloud Run API exposes `/health`, `/metrics`, `/docs`, and read-only
status routes. Mutations return HTTP 403. MLflow, ZenML, and retraining stay local.

Deploy or teardown: `deploy/gcp/README.md` and [PR-14/PR-15 evidence](../evidence/PR14_CLOUD_RUN_LIVE_DEMO.md).

## Teardown

```bash
make docker-down
make k8s-down
make obs-k8s-down
make lineage-down
make observability-down
```

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `make k8s-up` OOM | InvenTree Compose still running | `make docker-down`, retry |
| Dashboard sections "missing" | Artifacts not generated | Run `make reviewer-demo` |
| `/health` returns 503 locally | Artifacts absent | Run the ML/MLOps pipeline first |
| `obs-k8s-smoke` fails | Port-forwards not running | `make obs-k8s-port-forward` in another terminal |
| `lineage-smoke` fails | Marquez API not reachable | `make lineage-port-forward` first |

## Key concepts (reviewer cheat sheet)

| Term | Meaning in InvForge |
|------|---------------------|
| **Synthetic data** | CSVs generated locally (seed 42). Not real inventory. |
| **Stockout risk** | Simulated score from forecast error + lead time + on-hand. |
| **p10 / p50 / p90** | Forecast quantiles used for safety stock and reorder logic. |
| **MLflow** | Local experiment tracking (`mlruns/`). |
| **Evidently** | Drift/quality reports in `artifacts/mlops/evidently/`. |
| **ZenML** | Local retraining orchestration (`.zenml_local/`). |
| **BentoML** | Champion model packaging summary (`artifacts/mlops/bentoml/`). |

## Safe claims

- "Local synthetic pipeline runs deterministically with seed 42."
- "Live read-only API and reviewer dashboard are on Cloud Run."
- "Mutation endpoints are blocked in demo/cloud mode."
- "Simulated cost metrics are backtest diagnostics — not production ROI."

## Not safe claims

- "Deployed to production"
- "Real inventory cost savings"
- "Full observability/lineage validated" (unless you ran the live kind profiles)

## More reading

- [Backend and ML explainer](backend-and-ml-explainer.md)
- [Demo scenario](../../examples/demo-scenario/README.md)
- [Deployment contract](../deployment-contract.md)
