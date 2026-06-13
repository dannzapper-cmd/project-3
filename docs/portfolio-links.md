# Portfolio integration links (Project 4 readiness)

Copy-paste blocks for the Project 4 portfolio site. **Do not modify Project 4
from this repo** — consume these links/copy when updating it.

---

## Cloud Demo

| Field | Value |
|-------|-------|
| **Label** | Live InvForge Dashboard |
| **URL** | https://invforge-dashboard-demo-lwcelvo7ya-uc.a.run.app |
| **Username** | `reviewer` |
| **Password** | `invforge-demo` |
| **Note** | Read-only synthetic demo · guided scenarios · view-only sample inputs · reviewer gate only · not production auth |
| **Evidence screenshots** | [`docs/evidence/screenshots/cloud-dashboard/`](https://github.com/dannzapper-cmd/project-3/tree/main/docs/evidence/screenshots/cloud-dashboard) |

## Local Demo

| Field | Value |
|-------|-------|
| **Label** | Full Local Pipeline Demo |
| **Guide** | https://github.com/dannzapper-cmd/project-3/blob/main/docs/REVIEWER_DEMO_GUIDE.md |
| **Commands** | `uv sync --group dev --group pipeline --group ml --group mlops --group dashboard --group observability && make reviewer-demo && make dashboard` |
| **Note** | Complete local ML/MLOps pipeline · opens http://localhost:8501 |

## Existing links

| Field | Value |
|-------|-------|
| **GitHub** | https://github.com/dannzapper-cmd/project-3 |
| **API Docs** | https://invforge-ai-demo-lwcelvo7ya-uc.a.run.app/docs |
| **Case Study / Evidence** | https://github.com/dannzapper-cmd/project-3/blob/main/docs/evidence/PR14_CLOUD_RUN_LIVE_DEMO.md |
| **Reviewer Guide** | https://github.com/dannzapper-cmd/project-3/blob/main/docs/REVIEWER_DEMO_GUIDE.md |

## Portfolio-safe one-liner

> External AI ops sidecar over InvenTree — forecasting, MLOps, observability,
> security, **live read-only dashboard + API demo**, with full local pipeline.

## Honest caveats (include near demo CTAs)

- All data is **synthetic** (seed 42)
- Cloud surfaces are **read-only**; mutations blocked
- MLflow, ZenML, InvenTree admin are **local-only**
- Cost metrics are **simulated backtest diagnostics**, not real ROI
- Demo login is a **reviewer gate**, not production security
