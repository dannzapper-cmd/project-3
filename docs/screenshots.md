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
| `dashboard-overview.png` | http://localhost:8501 | Streamlit dashboard loads; artifact status cards green after `make demo-local` | Production monitoring; real inventory data |
| `dashboard-decision-intelligence.png` | http://localhost:8501 | Decision intel section: reorder recs, stockout risk, simulated cost context | Real dollar savings; live ERP integration |
| `dashboard-mlops.png` | http://localhost:8501 | MLOps section: drift, registry, BentoML status | Managed MLflow/ZenML in cloud |
| `api-health.png` | http://localhost:8001/health | API health payload with artifact summaries | Cloud deployment; authenticated access |
| `api-docs.png` | http://localhost:8001/docs | FastAPI OpenAPI UI for deployable read-only surface | Mutation endpoints enabled |
| `grafana-observability.png` | http://localhost:3000 | Local Grafana after `make observability-up` | Production SLOs; managed Grafana |
| `marquez-lineage.png` | Marquez UI (kind port-forward) | OpenLineage lineage for retraining job | Production data catalog |
| `github-actions-green.png` | GitHub Actions UI | CI/deploy/security checks green | PR-13 checks until pushed and verified |
| `terminal-demo-local-pass.png` | Terminal | `make demo-local` completes successfully | Full k8s/obs/lineage stack |

## Commands used per screenshot

### Dashboard and API (automated script)

```bash
make demo-local
# Script starts in background:
uv run --group dashboard streamlit run dashboard/app.py --server.headless true --server.port 8501
uv run --group observability uvicorn api.main:app --host 127.0.0.1 --port 8001
# Playwright captures pages at the URLs above
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

### GitHub Actions (manual export)

1. Push PR branch
2. Open https://github.com/dannzapper-cmd/project-3/actions
3. Screenshot green CI + Deploy Validation + Security workflows
4. Save as `docs/assets/screenshots/github-actions-green.png`

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

- Live GCP/AWS/Azure deployment (templates only)
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
