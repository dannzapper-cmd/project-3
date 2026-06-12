# InvForge — Screenshots

Portfolio screenshots live in [`docs/assets/screenshots/`](assets/screenshots/).
All images are captured from **locally running services** — not mocked.

Regenerate:

```bash
bash scripts/capture_pr13_screenshots.sh
# or: python3 scripts/capture_pr13_screenshots.py
```

See [`SCREENSHOT_MANIFEST.md`](assets/screenshots/SCREENSHOT_MANIFEST.md) for the latest run status.

## Screenshot list

| File | Service URL | What it proves | What it does NOT prove |
|------|-------------|----------------|------------------------|
| `system-flow.png` | http://localhost:8501 | **Backend pipeline chain** — dashboard section 0 shows data→ML→MLOps artifact paths | That observability/lineage ran in demo-local |
| `dashboard-overview.png` | http://localhost:8501 | Artifact status cards green after `make demo-local` | Production monitoring; real inventory data |
| `dashboard-decision-intelligence.png` | http://localhost:8501 | Decision intel section: reorder recs, stockout risk, simulated cost context | Real dollar savings; live ERP integration |
| `dashboard-mlops.png` | http://localhost:8501 | MLOps section: drift, registry, BentoML status | Managed MLflow/ZenML in cloud |
| `api-health.png` | http://localhost:8001/health | API health payload with artifact summaries | Cloud deployment; authenticated access |
| `api-docs.png` | http://localhost:8001/docs | FastAPI OpenAPI UI for deployable read-only surface | Mutation endpoints enabled |
| `grafana-observability.png` | http://localhost:3000 | Local Grafana after `make observability-up` | Production SLOs; managed Grafana |
| `marquez-lineage.png` | Marquez UI (kind port-forward) | OpenLineage lineage for retraining job | Production data catalog |
| `github-actions-green.png` | GitHub PR checks UI | CI + Deploy Validation + Security green on PR #17 | Future PRs until re-verified |
| `terminal-demo-local-pass.png` | `make demo-local` output | Full offline pipeline completes; dashboard smoke passes | Full k8s/obs/lineage stack |
| `cloud-run-health.png` | Cloud Run `/health` | Live read-only API returns 200 in demo mode | Production deployment; local artifacts bundled |
| `cloud-run-docs.png` | Cloud Run `/docs` | Live OpenAPI UI on Cloud Run | Mutation endpoints enabled |
| `cloud-run-mutation-blocked.png` | POST ingest 403 | Mutation blocking verified on live service | WAF or auth layer |

## Commands used per screenshot

### Dashboard and API (automated script)

```bash
make demo-local
# Script starts in background:
uv run --group dashboard streamlit run dashboard/app.py --server.headless true --server.port 8501
uv run --group observability uvicorn api.main:app --host 127.0.0.1 --port 8001
# Playwright captures: system-flow, overview, decision intel, MLOps, API health/docs
```

### Grafana (automated if Docker available)

```bash
make observability-up
# Playwright logs into Grafana (admin/admin, dev-only) and captures /dashboards
make observability-down
```

### Marquez (manual — kind profile)

```bash
make docker-down          # free RAM on 8 GB Mac
make lineage-up
make lineage-port-forward # note Marquez UI port from script output
# Browser: open Marquez UI → search invforge.retraining
make lineage-down
```

### GitHub Actions (automated or manual)

Automated (public PR checks page):

```bash
# Included in scripts/capture_pr13_screenshots.py — PR #17 checks URL
```

Manual fallback:

1. Open https://github.com/dannzapper-cmd/project-3/pull/17/checks
2. Screenshot green CI + Deploy Validation + Security
3. Save as `docs/assets/screenshots/github-actions-green.png`

### Terminal demo-local (manual or log)

```bash
make demo-local 2>&1 | tee /tmp/demo-local.log
# Screenshot terminal showing "Dashboard smoke: all loader contract checks passed."
```

Automated fallback: script writes `docs/assets/screenshots/demo-local-pass.log`.

## What is proven vs not proven

**Proven (with captured screenshots + PR-12.6 evidence):**

- Local pipeline produces artifacts and dashboard renders them
- API `/health` and `/docs` work with real artifact summaries
- Local Grafana stack starts and serves dashboards
- Offline deploy profile validation passes

**Not proven by screenshots alone:**

- Live AWS/Azure deployment (GCP Cloud Run read-only API is live — see PR-14)
- Production auth, WAF, or network isolation
- Real InvenTree ingestion with customer data
- Managed Kubernetes (GKE/EKS/AKS)
- Video walkthrough (manual/future)

## Manual fallback checklist

If Playwright install fails or ports are in use:

1. Run `make demo-local`
2. `make dashboard` → capture Overview, Decision Intelligence, MLOps sections (scroll)
3. `make observability-api` → capture `/health`, `/docs` in browser
4. `make observability-up` → capture Grafana login/dashboards
5. Optional kind: `make lineage-up` → capture Marquez
6. Save PNGs to `docs/assets/screenshots/` with names matching the table above
7. Update `SCREENSHOT_MANIFEST.md` with PASS/MANUAL status

## Compression

PNG files should be reasonably sized (< 500 KB each where possible). Re-export
with compression if files exceed ~1 MB.
