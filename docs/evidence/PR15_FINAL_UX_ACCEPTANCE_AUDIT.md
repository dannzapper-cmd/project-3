# PR-15 — Final UX acceptance audit

Date: 2026-06-12  
Repo: `/Users/danny/project-3-clean`  
Branch: `cursor/pr15-final-ux-acceptance-audit`  
Scope: Reviewer-facing UX/docs polish only — no features, no cloud changes.

## Summary

Final acceptance pass confirming the InvForge demo **self-explains** the
backend/ML/MLOps flow, local and live surfaces are clearly separated, and cost
guardrails are documented. Minor copy fixes only (dashboard limitations, demo
script Cloud Run section, cost guardrail docs).

## Commands run

| Command | Result |
|---------|--------|
| `git fetch && checkout main && pull --ff-only` | **PASS** (HEAD `017b228`) |
| `make demo-local` | **PASS** (~65 s) |
| `make dashboard-smoke` | **PASS** — all loader contract checks |
| `make observability-api` + `curl /health` + `curl /docs` | **PASS** — HTTP 200, artifacts ok |
| Cloud Run `curl /health` | **PASS** — HTTP 200, artifacts missing (expected) |
| Cloud Run `curl /docs` | **PASS** — HTTP 200 |
| Cloud Run `POST /v1/ingest/inventree` | **PASS** — HTTP 403, no secrets in body |
| Screenshot file sanity (`file` on 13 PNGs) | **PASS** — all valid PNG |
| `uv run ruff check .` | **PASS** (post-change) |
| `uv run pytest` | **PASS** (post-change) |
| `make secrets-scan` | **PASS** (post-change) |
| `make security-check` | **PASS** (post-change) |

## Dashboard clarity verdict (2-minute reviewer test)

| Question | Clear? | Where answered |
|----------|--------|----------------|
| 1. Default data source | **Yes** | Section 0 step 1 — synthetic CSVs seed 42 |
| 2. Command generating artifacts | **Yes** | Section 0 — `make demo-local` chain + per-step `make` targets |
| 3. ML models | **Yes** | Step 3 — LightGBM + StatsForecast + Croston/SBA |
| 4. Decision intelligence | **Yes** | Step 4 + section 3 — safety stock, ROP, EOQ, stockout risk |
| 5. Artifacts dashboard reads | **Yes** | Section 0 artifact paths + loaders in `dashboard/paths.py` |
| 6. What API proves | **Yes** | Companion step 6 + README + backend explainer |
| 7. What Cloud Run proves | **Yes** | README Live API Demo + demo-script §8 + quick walkthrough table |
| 8. What is local-only | **Yes** | Section 0 info box, limitations §5, README |
| 9. What is not production | **Yes** | Warning banner, limitations, simulated cost disclaimers |
| 10. Business case | **Yes** | README business case + case study |

**Fix applied:** Dashboard section 5 still referenced deferred PR-07/10/11 —
updated to current local-only / live-API scope language.

## Screenshot status

All 13 portfolio PNGs exist and are valid (no recapture needed — copy changes
did not alter dashboard layout):

| File | Status |
|------|--------|
| `system-flow.png` | **VALID** |
| `dashboard-overview.png` | **VALID** |
| `dashboard-decision-intelligence.png` | **VALID** |
| `dashboard-mlops.png` | **VALID** |
| `api-health.png` | **VALID** |
| `api-docs.png` | **VALID** |
| `grafana-observability.png` | **VALID** |
| `marquez-lineage.png` | **VALID** |
| `github-actions-green.png` | **VALID** |
| `terminal-demo-local-pass.png` | **VALID** |
| `cloud-run-health.png` | **VALID** |
| `cloud-run-docs.png` | **VALID** |
| `cloud-run-mutation-blocked.png` | **VALID** |

## Local flow status

- `make demo-local` completes end-to-end (generate → validate → train → decision → MLOps → smoke)
- Dashboard section **0. How InvForge Works** present in `dashboard/app.py`
- Artifact-backed status cards green after pipeline run
- Local API `/health` returns `status: ok` with artifact summaries when pipeline ran first

## Live API status

| Check | Result |
|-------|--------|
| Service URL | https://invforge-ai-demo-289428962093.us-central1.run.app |
| `GET /health` | HTTP **200** (`status: unavailable` — no bundled artifacts; expected) |
| `GET /docs` | HTTP **200** |
| `POST /v1/ingest/inventree` | HTTP **403** — mutation blocked |
| Secrets in responses | **None observed** |

## Cost guardrail status

Documented in PR-14 evidence, GCP activation guide, and `docs/costs/deployment-costs.md`:

- `min-instances: 0`, `max-instances: 1`
- Teardown: `gcloud run services delete invforge-ai-demo --region us-central1`
- Keep live only during job-search period
- Artifact Registry storage may have minor cost
- No GKE / DB / VM / Redis / load balancer in default profile

## Changes made (minimal)

| Path | Change |
|------|--------|
| `dashboard/app.py` | Replace stale PR-deferred limitations with current scope copy |
| `docs/demo-script.md` | §8 — live Cloud Run links + local-vs-cloud clarity |
| `docs/tutorials/quick-demo-walkthrough.md` | Local dashboard vs live API table |
| `docs/evidence/PR14_CLOUD_RUN_LIVE_DEMO.md` | Cost guardrail table |
| `docs/cloud/gcp-cloud-run-activation.md` | Guardrail bullets |
| `docs/costs/deployment-costs.md` | PR-14 live demo + guardrails section |

## Remaining caveats

- Cloud Run `/health` JSON shows `status: unavailable` without local artifacts — reviewers must read README/docs for expected demo-mode behavior
- GitHub Actions screenshot references PR #17 checks — re-verify on future PRs
- Marquez screenshot from prior kind capture (not re-run this audit)
- No production auth on read-only API routes
- Synthetic data only; no real ROI claims

## Final portfolio readiness verdict

**READY** for portfolio web use. A reviewer can run `make demo-local`, open the
local dashboard to see the backend pipeline chain, hit local or live API endpoints,
and understand what is demo vs production within ~2 minutes. Live Cloud Run proves
deployable read-only surface; mutation blocking verified.
