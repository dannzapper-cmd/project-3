# Quick demo walkthrough — InvForge from zero

This guide helps a reviewer run InvForge locally, understand what they are seeing,
and know which claims are safe to make. All commands come from the repo
`Makefile` — run `make help` for the full list.

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
make demo-local
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

Observability-only (smoke backends, no alert loop):

```bash
make k8s-up && make k8s-deploy
make obs-k8s-up
make obs-k8s-status
make obs-k8s-port-forward   # separate terminal
make obs-k8s-smoke
make obs-k8s-down
make k8s-down
```

Full alert loop (AI + observability together — needs ~8 GB+ RAM, sequential):

```bash
make k8s-preflight
make k8s-up
make k8s-deploy
make k8s-smoke
make obs-k8s-up
make obs-k8s-port-forward   # separate terminal; wait for pods Ready first
make obs-k8s-smoke
make obs-k8s-alert-test     # scales AI to 0, verifies webhook receives InvForgeAIDown
make obs-k8s-down
make k8s-down
```

Or use the evidence collector:

```bash
bash scripts/collect_pr12_6_evidence.sh --observability-combined
```

## Optional lineage profile (PR-11B)

```bash
make lineage-up
make lineage-port-forward   # separate terminal
make lineage-smoke
make lineage-down
```

## Local dashboard vs live read-only API

| Surface | Where it runs | Command / URL |
|---------|---------------|---------------|
| Streamlit dashboard | **Local only** | `make dashboard` → http://localhost:8501 |
| FastAPI (full artifacts) | **Local** | `make observability-api` → http://localhost:8001 |
| FastAPI (read-only demo) | **Live Cloud Run** | https://invforge-ai-demo-289428962093.us-central1.run.app |

The live Cloud Run service exposes **only** `/health`, `/metrics`, `/docs`, and
read-only status routes. It does not bundle ML artifacts, the dashboard, or
InvenTree. Mutations return HTTP 403.

To deploy your own instance (or tear down the portfolio demo), see
`deploy/gcp/README.md` and [PR-14 evidence](../evidence/PR14_CLOUD_RUN_LIVE_DEMO.md).
AWS ECS/Fargate and Azure Container Apps remain activation-ready templates.

## Teardown

```bash
make docker-down              # InvenTree Compose
make k8s-down                 # kind cluster
make obs-k8s-down             # observability namespace
make lineage-down             # lineage namespace
make observability-down       # local Prometheus/Grafana compose
```

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `make k8s-up` OOM | InvenTree Compose still running | `make docker-down`, retry |
| Dashboard sections "missing" | Artifacts not generated | Run `make train-ml`, `decision-intel`, `mlops-loop` |
| `/health` returns 503 locally | Artifacts absent | Run the ML/MLOps pipeline first |
| `obs-k8s-smoke` fails | Port-forwards not running | `make obs-k8s-port-forward` in another terminal |
| `lineage-smoke` fails | Marquez API not reachable | `make lineage-port-forward` first |

## Key concepts (reviewer cheat sheet)

| Term | Meaning in InvForge |
|------|---------------------|
| **Synthetic data** | CSVs generated locally (seed 42). Not real inventory. Regenerated by `make generate-data`. |
| **Stockout risk** | Simulated score from forecast error + lead time + on-hand. Ranks SKUs for review — not a live ERP alert. |
| **p10 / p50 / p90** | Forecast quantiles: pessimistic (10th), median (50th), optimistic (90th) demand. Used for safety stock and reorder logic. |
| **MLflow** | Local experiment tracking (`mlruns/`). Logs metrics, params, and model artifacts per training run. |
| **Evidently** | Drift/quality reports in `artifacts/mlops/evidently/`. Feeds the MLOps dashboard section and `/health` drift flag. |
| **ZenML** | Local orchestration for the PR-09 retraining DAG (SQLite metadata in `.zenml_local/`). |
| **BentoML** | Packages the champion model into a deployable bundle summary (`artifacts/mlops/bentoml/`). k8s serving is opt-in. |

## What outputs mean

| Output | Meaning |
|--------|---------|
| `artifacts/decision/decision_summary.json` | Simulated reorder / stockout diagnostics |
| `artifacts/mlops/champion_challenger/comparison.json` | Champion vs challenger metrics |
| `artifacts/mlops/mlops_loop_summary.json` | Drift flag, registry strategy |
| `/health` payload | Artifact presence + drift/champion decision summary |
| `/metrics` | Prometheus exposition (when observability group installed) |

## What is synthetic vs real

| Synthetic (demo default) | Real (opt-in) |
|--------------------------|---------------|
| `data/synthetic/output/*` CSVs | InvenTree inventory via `POST /v1/ingest/inventree` |
| Forecasts and cost reductions | Backtest diagnostics only — not real savings |
| Local MLflow / ZenML metadata | No production registry |

## Safe claims

- "Local synthetic pipeline runs deterministically with seed 42."
- "Read-only API surfaces exist for health, metrics, and inventory status."
- "Cloud deploy profiles are activation-ready templates; GCP Cloud Run is the documented primary target."
- "Mutation endpoints are blocked in demo/cloud mode."

## Not safe claims

- "Deployed to production" (unless you have a live URL and evidence)
- "Real inventory cost savings"
- "Full observability/lineage validated" (unless you ran the live kind profiles)

## More reading

- [Backend and ML explainer](backend-and-ml-explainer.md)
- [Demo scenario](../../examples/demo-scenario/README.md)
- [PR-12 audit](../audits/pr12-full-qa-audit.md)
- [Deployment contract](../deployment-contract.md)
