# InvForge Reviewer Demo Guide

> **Synthetic data only · read-only cloud demo · no real savings claims**

This guide is for recruiters, hiring managers, and technical reviewers who want to
evaluate InvForge quickly — browser-only, full local, or advanced profiles.

---

## 1. Choose your path

| Path | Time | Install? | Best for |
|------|------|----------|----------|
| **A. Browser-only cloud** | ~5 min | No | First impression, live dashboard + API |
| **B. Full local demo** | ~15–20 min | Yes (uv + Make) | Complete ML/MLOps pipeline + dashboard |
| **C. Advanced local** | 30+ min | Yes (+ Docker/k8s) | InvenTree, Grafana, kind, security audit |

---

## 2. Cloud demo (browser-only)

### Live read-only dashboard

| | |
|---|---|
| **URL** | https://invforge-dashboard-demo-lwcelvo7ya-uc.a.run.app |
| **Username** | `reviewer` |
| **Password** | `invforge-demo` |
| **Verified** | 2026-06-12 |

> **Reviewer gate only — not production authentication.** These credentials unlock
> synthetic read-only dashboard content only.

**After login you should see:**

1. **Reviewer Mission Control** — what this is, what to click first, cloud vs local
2. **Guided Demo Scenarios** — three preloaded reviewer paths (stockout triage, forecast review, MLOps readiness)
3. **Sample Inputs** — view-only scenario YAML, API JSON, fixture SKUs, local commands
4. Mode label: **Cloud · fixture-backed read-only demo**
5. Yellow banner: **Read-only portfolio demo · synthetic data · not production**
6. **Overview** — status cards for Data, ML forecast, Decision intel, MLOps
7. Sections 2–4 — forecast chart, decision table, MLOps summary (no contradictory missing BentoML state)
8. **Observability & API health** — live cloud API health (in expander)

> **Mobile:** usable for login and first impression; desktop recommended for charts/tables.

**What the cloud dashboard is NOT:**

- Not live MLflow, ZenML, or InvenTree
- Not training models on cold start
- Not a mutation/admin surface
- Not real inventory or ROI data

Cloud content comes from **bundled synthetic fixtures** (~116 KB, seed 42) baked
into the container — intentionally truncated for cost and security.

### Live read-only API

| | |
|---|---|
| **OpenAPI** | https://invforge-ai-demo-lwcelvo7ya-uc.a.run.app/docs |
| **Health** | https://invforge-ai-demo-lwcelvo7ya-uc.a.run.app/health |
| **Metrics** | https://invforge-ai-demo-lwcelvo7ya-uc.a.run.app/metrics |

Try `GET /health` and `GET /v1/inventory/status`. Confirm
`POST /v1/ingest/inventree` returns **403** (mutations blocked in cloud mode).

### Safer password for non-public deploys

For portfolio demo, `invforge-demo` is an intentionally public low-privilege gate.
For private deploys, set `INVFORGE_DEMO_PASSWORD` from **GCP Secret Manager** and
do not document the password publicly. See
[`docs/cloud/gcp-cloud-run-activation.md`](cloud/gcp-cloud-run-activation.md).

---

## 3. Local demo quickstart

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- Make

### Commands

```bash
git clone https://github.com/dannzapper-cmd/project-3.git
cd project-3
uv sync --group dev --group pipeline --group ml --group mlops --group dashboard --group observability
cp app/.env.example app/.env
make reviewer-demo
make dashboard
```

Open **http://localhost:8501** — all four overview cards should be green after
`reviewer-demo` completes.

### Optional API (second terminal)

```bash
make observability-api
curl -s http://localhost:8001/health | python -m json.tool
curl -s http://localhost:8001/metrics | head -20
```

Open **http://localhost:8001/docs** for local OpenAPI.

### Test dashboard auth locally (optional)

Local dashboard runs **without auth by default**. To test the cloud login gate:

```bash
INVFORGE_DEMO_AUTH_ENABLED=true \
INVFORGE_DEMO_USER=reviewer \
INVFORGE_DEMO_PASSWORD=invforge-demo \
make dashboard
```

---

## 4. Demo credentials

| Surface | Credentials | Notes |
|---------|-------------|-------|
| **Cloud dashboard** | `reviewer` / `invforge-demo` | Reviewer gate; synthetic read-only only |
| **Local dashboard** | None (default) | Enable auth with env vars above |
| **Cloud API** | None | Public read-only; mutations blocked |
| **InvenTree admin** | Local Docker only | Create via `cd app && docker compose run --rm inventree-server invoke superuser` — never expose publicly |

Never commit real tokens or passwords. `app/.env.example` uses placeholders only.

---

## 5. What backend runs locally

`make reviewer-demo` runs this chain (deterministic seed 42):

| Step | Command (internal) | Output |
|------|-------------------|--------|
| 1. Synthetic data | `make generate-data` | `data/synthetic/output/*.csv` |
| 2. ML training | `make train-ml` | `mlruns/` (local MLflow file store) |
| 3. Decision intel | `make decision-intel` | `artifacts/decision/` |
| 4. MLOps loop | `make mlops-loop` | `artifacts/mlops/` (drift, registry, BentoML summary) |
| 5. Dashboard | `make dashboard` | Reads artifacts above — **does not retrain** |
| 6. API (optional) | `make observability-api` | `/health`, `/metrics`, status endpoints |

**Optional advanced local profiles:**

- **InvenTree base stack:** `make docker-up && make docker-init`
- **Prometheus + Grafana:** `make observability-up` → http://localhost:3000
- **Security audit:** `make security-audit`
- **Kubernetes AI layer:** `make k8s-up && make k8s-deploy` (8 GB RAM warning)

---

## 6. What backend runs in cloud

| Component | Cloud | Local |
|-----------|-------|-------|
| Streamlit dashboard | Yes — read-only, fixture-backed | Yes — full artifacts |
| FastAPI AI Ops API | Yes — read-only | Yes |
| ML training / retraining | **No** | Yes |
| MLflow / ZenML UI | **No** | Yes (file store / local stack) |
| InvenTree ERP | **No** | Yes (Docker Compose) |
| Mutation endpoints | **Blocked (403)** | Allowed in local mode |
| Prometheus / Grafana | **No** | Yes (optional Docker stack) |

Cloud Run services scale to zero when idle. Cold starts are normal for portfolio
demo cost control.

---

## 7. Sample inputs and demo story

| File | Purpose |
|------|---------|
| [`examples/demo-scenario/scenario.yaml`](../examples/demo-scenario/scenario.yaml) | Pipeline steps + SKU stories |
| [`examples/api/forecast_request.json`](../examples/api/forecast_request.json) | Sample API context + expected cloud responses |

**SKU story (synthetic seed 42):**

- **PRT-0001** — stable SKU, steady demand
- **PRT-0015** — intermittent demand (Croston-family candidate)
- **PRT-0088** — rising stockout risk in recommendations table
- **PRT-0042** — long lead time, higher reorder point

After `make reviewer-demo`, open the dashboard **Decision Intelligence** section
and sort by risk to find these patterns in `decision_recommendations.csv`.

---

## 8. Troubleshooting

| Issue | Fix |
|-------|-----|
| Dashboard sections show **missing** | Run `make reviewer-demo` first |
| `uv sync` fails | Ensure Python 3.12+; retry with `--group` flags from quickstart |
| Port 8501 in use | `streamlit run dashboard/app.py --server.port 8502` |
| Port 8001 in use | `INVFORGE_API_PORT=8002 make observability-api` |
| Docker daemon not running | Required only for `docker-*`, InvenTree, observability-up |
| Cloud dashboard cold start | Wait 10–30s on first request after idle |
| Auth password typo | Cloud: `reviewer` / `invforge-demo` (exact, lowercase) |
| API health 503 locally | Normal without artifacts; use cloud URL or run `reviewer-demo` |
| k8s OOM on 8 GB laptop | Stop InvenTree first: `make docker-down` |

---

## 9. Teardown

```bash
# Local processes
# Ctrl+C in terminals running dashboard / API

make observability-down   # if Prometheus/Grafana started
make docker-down          # if InvenTree started
make k8s-down             # if kind cluster started

# Cloud dashboard
export PROJECT_ID=your-project REGION=us-central1
./deploy/gcp/dashboard.teardown.example.sh

# Cloud API (if you deployed it)
./deploy/gcp/teardown.example.sh
```

**Cost note:** Cloud Run `minScale: 0` avoids always-on charges. You may still
incur small costs for image storage, requests while active, and egress. Verify
current GCP pricing before deploying.

---

## 10. Safe claims vs unsafe claims

| Safe to say | Do NOT claim |
|-------------|--------------|
| Read-only cloud dashboard + API demo | Production-grade security from demo login |
| Synthetic seed-42 pipeline (local) | Real customer inventory or savings |
| Forecasting + decision intel artifacts | Public full ERP / MLflow / ZenML access |
| MLOps loop with drift/registry evidence | Real-world ROI from simulated cost metrics |
| Sidecar over InvenTree (core untouched) | Modified InvenTree core |

---

**Related:** [`docs/portfolio-links.md`](portfolio-links.md) · [`docs/demo-script.md`](demo-script.md) · [`docs/tutorials/quick-demo-walkthrough.md`](tutorials/quick-demo-walkthrough.md)
