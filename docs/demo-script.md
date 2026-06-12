# InvForge — 5–8 minute demo script

Use this script for a portfolio review, live walkthrough, or recorded video.
All commands are copy-paste ready.

**Duration:** ~6 minutes at a comfortable pace.

---

## 1. Opening pitch (~45 s)

> InvForge is an AI Operations sidecar for inventory teams. It sits **outside**
> InvenTree — we never modify the core ERP — and turns demand history into
> forecast-informed decisions: stockout risk, reorder recommendations, model
> health checks, and auditable evidence.
>
> The cloud demo is **read-only** with **synthetic data**. The full ML/MLOps
> pipeline runs locally. We do not claim real-world savings — cost figures are
> simulated backtest diagnostics.

---

## 2. Path A — Live cloud (no install, ~5 min)

1. **Dashboard:** https://invforge-dashboard-demo-lwcelvo7ya-uc.a.run.app
   - Sign in: `reviewer` / `invforge-demo`
   - Point out read-only banner
   - Walk Overview → Forecast → Decision → MLOps → API health
2. **API docs:** https://invforge-ai-demo-lwcelvo7ya-uc.a.run.app/docs
3. Run `GET /health` — show artifact flags and read-only posture
4. Run `GET /v1/inventory/status`
5. Show `POST /v1/ingest/inventree` returns **403**

---

## 3. Path B — Full local (~15 min)

```bash
uv sync --group dev --group pipeline --group ml --group mlops --group dashboard --group observability
cp app/.env.example app/.env   # optional — only if showing InvenTree stack
make reviewer-demo
make dashboard
```

Say while `reviewer-demo` runs:

- Generates deterministic synthetic inventory CSVs (seed 42)
- Validates with Pandera
- Trains LightGBM + StatsForecast baselines
- Runs decision intelligence and MLOps loop
- Smoke-tests dashboard loaders

Open `http://localhost:8501`.

### Panel walkthrough

0. **Cloud vs local / pipeline chain** — backend already ran; UI is read-only proof
1. **Overview** — four status cards: Data, ML forecast, Decision intel, MLOps
2. **Forecast Performance** — champion vs challenger; p10/p50/p90 quantiles
3. **Decision Intelligence** — top reorder recommendations; highlight high stockout risk SKUs
4. **MLOps Status** — drift flag, registry strategy, BentoML packaging
5. **Limitations** — synthetic data, no real savings claims

Highlight sample inputs:

- `examples/demo-scenario/scenario.yaml`
- `examples/api/forecast_request.json`

---

## 4. API health and metrics (~45 s)

New terminal:

```bash
make observability-api
```

```bash
curl -s http://localhost:8001/health | python -m json.tool
curl -s http://localhost:8001/v1/inventory/status | python -m json.tool
curl -s http://localhost:8001/metrics | head -20
```

Open `http://localhost:8001/docs` — read-only FastAPI surface.

---

## 5. MLOps evidence (~45 s, optional)

```bash
make retrain-smoke
make retraining-check
cat artifacts/mlops/mlops_loop_summary.json | python -m json.tool
```

Say: *"Retraining runs locally via ZenML with gated promotion. Evidence of MLOps
discipline, not a hosted production platform."*

---

## 6. Observability and lineage (~60 s, optional)

```bash
make observability-up    # Grafana http://localhost:3000 (admin/admin, dev-only)
# or kind profiles: make obs-k8s-up && make obs-k8s-port-forward
```

Teardown when done: `make observability-down`

---

## 7. Cloud readiness (~30 s)

Point to the **live read-only surfaces** (already deployed):

- Dashboard: https://invforge-dashboard-demo-lwcelvo7ya-uc.a.run.app
- API: https://invforge-ai-demo-lwcelvo7ya-uc.a.run.app/docs

```bash
curl -fsS https://invforge-ai-demo-lwcelvo7ya-uc.a.run.app/health
curl -I https://invforge-dashboard-demo-lwcelvo7ya-uc.a.run.app/_stcore/health
make deploy-validate
```

Say: *"Cloud Run hosts read-only API + reviewer dashboard. MLflow, ZenML, and
retraining stay local. Mutations are blocked."*

---

## 8. Close — limitations (~45 s)

> **Honest caveats:**
> - Synthetic data; no production ROI claims
> - Demo login is a reviewer gate, not production auth
> - kind Kubernetes is local evidence, not managed GKE/EKS/AKS
>
> **Next in production:** managed auth, IaC, real InvenTree integration with
> secret rotation, scheduled retraining, SLOs, and cost governance.

Guide: [`REVIEWER_DEMO_GUIDE.md`](REVIEWER_DEMO_GUIDE.md)

---

## Quick reference

| Step | Command | URL |
|------|---------|-----|
| Reviewer pipeline | `make reviewer-demo` | — |
| Dashboard | `make dashboard` | http://localhost:8501 |
| API | `make observability-api` | http://localhost:8001 |
| Live dashboard | browser | https://invforge-dashboard-demo-lwcelvo7ya-uc.a.run.app |
| Live API docs | browser | https://invforge-ai-demo-lwcelvo7ya-uc.a.run.app/docs |

See also: [quick demo walkthrough](tutorials/quick-demo-walkthrough.md),
[case study](case-study.md), [screenshots](screenshots.md).
