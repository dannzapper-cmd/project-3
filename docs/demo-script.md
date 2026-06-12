# InvForge — 5–8 minute demo script

Use this script for a live walkthrough or to record a portfolio video later.
All commands are copy-paste ready. **No video automation** — record manually.

**Duration:** ~6 minutes at a comfortable pace.

---

## 1. Opening pitch (~45 s)

> InvForge is an AI Operations sidecar for inventory teams. It sits **outside**
> InvenTree — we never modify the core ERP — and turns demand history into
> forecast-informed decisions: stockout risk, reorder recommendations, model
> health checks, and auditable evidence.
>
> The business value is **decision support**, not autonomous magic: faster ops
> review cycles, clearer risk flags, and a deployable read-only API that
> technical teams can run beside their existing inventory system.
>
> Everything in this demo uses **synthetic data** unless I explicitly connect
> to a live InvenTree instance.

---

## 2. Local setup (~30 s)

```bash
cd /path/to/invforge
uv sync --group dev --group pipeline --group ml --group mlops --group dashboard --group observability
cp app/.env.example app/.env   # optional — only if showing InvenTree stack
```

Say: *"Prerequisites are Docker, uv, and make. InvenTree is optional for the
synthetic demo path."*

---

## 3. Generate data and run the pipeline (~90 s)

```bash
make demo-local
```

Say while it runs:

- Generates deterministic synthetic inventory CSVs (seed 42)
- Validates with Pandera
- Trains LightGBM + StatsForecast baselines (including Croston/SBA for intermittent SKUs)
- Runs decision intelligence (safety stock, ROP, EOQ, stockout risk)
- Runs the MLOps loop (Evidently drift, MLflow registry, champion/challenger, BentoML packaging)
- Smoke-tests the dashboard loaders — no browser yet

Point to outputs:

```bash
ls data/synthetic/output/
ls artifacts/decision/ artifacts/mlops/
```

---

## 4. Launch the dashboard (~60 s)

```bash
make dashboard
```

Open `http://localhost:8501`.

### Panel walkthrough

0. **How InvForge Works (System Flow)** — shows the backend pipeline chain
   (`make demo-local`) and artifact paths this dashboard reads. Emphasize: *not a
   frontend-only demo — ML/MLOps already ran.*
1. **Overview** — four status cards: Data, ML forecast, Decision intel, MLOps. All should be green.
2. **Forecast Performance** — champion vs challenger metrics; emphasize p10/p50/p90 quantiles.
3. **Decision Intelligence** — top reorder recommendations; highlight `SKU-C330` / high stockout risk from [demo scenario](../examples/demo-scenario/README.md).
4. **MLOps Status** — drift flag, registry strategy, BentoML packaging status.
5. **Limitations** — scroll to the disclaimer: synthetic data, no real savings claims.

---

## 5. API health and metrics (~45 s)

New terminal:

```bash
make observability-api
```

In another terminal:

```bash
curl -s http://localhost:8001/health | jq .status,.artifacts
curl -s http://localhost:8001/v1/inventory/status | jq .status,.demo_mode
curl -s http://localhost:8001/metrics | head -20
```

Open in browser:

- `http://localhost:8001/docs` — FastAPI OpenAPI UI (read-only surface)
- `http://localhost:8001/health` — JSON health payload

Say: *"This is the deployable public surface — health, metrics, and read-only
status. Mutation endpoints are blocked in demo/cloud mode."*

---

## 6. MLOps and retraining evidence (~45 s)

```bash
# Optional — if time allows
make retrain-smoke
make retraining-check
```

Show artifacts:

```bash
cat artifacts/mlops/mlops_loop_summary.json | jq .drift_detected,.registry_strategy
ls artifacts/mlops/evidently/
```

Say: *"Retraining runs locally via ZenML with gated promotion and rollback.
This is evidence of MLOps discipline, not a hosted production platform."*

---

## 7. Observability and lineage (~60 s, optional)

**Lightweight path (Docker):**

```bash
make observability-up    # Grafana http://localhost:3000 (admin/admin, dev-only)
```

**Heavy path (kind, 8 GB Mac — run sequentially):**

```bash
make obs-k8s-up && make obs-k8s-port-forward   # Grafana on forwarded port
make lineage-up && make lineage-port-forward   # Marquez UI — invforge.retraining event
```

Say: *"Observability and lineage are local/dev profiles. Tempo tracing is
deployed but idle until we instrument the API."*

Teardown when done:

```bash
make observability-down
make obs-k8s-down
make lineage-down
```

---

## 8. Cloud readiness (~30 s)

Point to the **live read-only API** (already deployed — do not redeploy):

- [Health](https://invforge-ai-demo-289428962093.us-central1.run.app/health)
- [OpenAPI docs](https://invforge-ai-demo-289428962093.us-central1.run.app/docs)

```bash
curl -fsS https://invforge-ai-demo-289428962093.us-central1.run.app/health
curl -i -X POST https://invforge-ai-demo-289428962093.us-central1.run.app/v1/ingest/inventree  # expect 403
```

Say: *"Cloud Run hosts only the read-only API — dashboard, MLflow, ZenML, and
retraining stay local. Mutations are blocked. Keep the service live only during
job-search; tear down when done. See PR-14 evidence for cost guardrails."*

Optional — show activation templates without deploying:

```bash
make deploy-validate
ls deploy/gcp/ deploy/aws/ deploy/azure/
```

Optional container smoke:

```bash
make docker-smoke
```

---

## 9. Close — limitations and future work (~45 s)

> **Honest caveats:**
> - Synthetic data; no production ROI claims
> - Dashboard and MLflow are local-only
> - No production auth on the API — mutations blocked in cloud mode
> - kind Kubernetes is local evidence, not managed GKE/EKS/AKS
>
> **Next in production:** managed auth, IaC, real InvenTree integration with
> secret rotation, scheduled retraining, SLOs, and cost governance.

Stop dashboard/API:

```bash
# Ctrl+C on dashboard and observability-api terminals
```

---

## Quick reference

| Step | Command | URL |
|------|---------|-----|
| Pipeline | `make demo-local` | — |
| Dashboard | `make dashboard` | http://localhost:8501 |
| API | `make observability-api` | http://localhost:8001 |
| API docs | browser | http://localhost:8001/docs |
| Grafana (Docker) | `make observability-up` | http://localhost:3000 |
| Deploy validate | `make deploy-validate` | — |

See also: [quick demo walkthrough](tutorials/quick-demo-walkthrough.md),
[case study](case-study.md), [screenshots](screenshots.md).
