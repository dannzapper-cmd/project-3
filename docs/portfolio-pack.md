# InvForge — Portfolio pack

Copy blocks for portfolio sites, CVs, and interview prep. **Do not overclaim**
— see [limitations](limitations.md).

---

## Short portfolio description (~100 words)

InvForge is an AI Operations Control Tower — an external sidecar over InvenTree
that adds demand forecasting, decision intelligence, MLOps, observability, and
defensive security without modifying the inventory core. It turns synthetic
demand history into forecast-informed reorder recommendations, stockout risk
flags, and auditable model health evidence. The deployable surface is a
read-only FastAPI API (Cloud Run–ready templates); the Streamlit dashboard,
MLflow, and retraining pipelines run locally. Built as a 13-PR incremental
reference implementation with full QA evidence.

---

## Resume / CV block

```
InvForge — AI Operations Control Tower
Category: Applied AI / MLOps / Enterprise Integration

What it is:
External AI Operations sidecar over InvenTree (open-source inventory ERP).
Adds demand forecasting, inventory decision intelligence, MLOps loop,
observability, and defensive security — without modifying InvenTree core.

AI / technical signal:
- LightGBM + StatsForecast + Croston/SBA forecasting with p10/p50/p90 quantiles
- Decision intelligence: safety stock, ROP, EOQ, stockout risk from forecasts
- MLOps: MLflow registry, Evidently drift, champion/challenger, BentoML, ZenML retraining
- Observability: Prometheus/Grafana, kind LGTM stack, OpenLineage/Marquez lineage
- Defensive security: audit pipeline, CI secrets/vuln scanning, mutation blocking
- Cloud-ready deploy templates: GCP Cloud Run, AWS ECS Fargate, Azure Container Apps

Business impact (simulated / decision support — not production ROI):
- Ranked reorder recommendations and stockout risk flags for ops review cycles
- Simulated cost-aware backtest diagnostics vs naive baselines (synthetic data)
- Deployable read-only API for technical teams alongside existing ERP/inventory systems

Skills demonstrated:
Python · FastAPI · LightGBM · MLOps · Docker · Kubernetes (kind) · Helm ·
Prometheus/Grafana · Streamlit · CI/CD · Defensive security · Cloud deploy profiles

Stack:
Python 3.12 · uv · FastAPI · LightGBM · StatsForecast · MLflow · Evidently ·
ZenML · BentoML · Feast · Pandera · DVC · Streamlit · Prometheus · Grafana ·
OpenLineage/Marquez · Docker · kind · Helm · GitHub Actions

Links:
GitHub: https://github.com/dannzapper-cmd/project-3
Case study: docs/case-study.md
Demo video: [placeholder — record from docs/demo-script.md]
Live demo: [placeholder — activate Cloud Run manually from docs/cloud/]
```

---

## Interview talking points

### Architecture

- "InvForge is a **sidecar** — we never fork InvenTree. Integration is REST API or synthetic data."
- "The **deployable surface** is one read-only FastAPI container. Dashboard and MLflow are local."
- "Cloud Run is the **preferred low-cost target** because it scale-to-zeroes for portfolio demos."

### ML / forecasting

- "We classify SKUs by demand pattern and route intermittent items to **Croston/SBA**."
- "Decision intelligence uses **quantile forecasts**, not point estimates — p90 drives safety stock."
- "Cost metrics are **simulated backtests** with explicit warnings — I never claim real savings."

### MLOps

- "The loop runs Evidently drift → MLflow registry → champion/challenger → BentoML packaging."
- "Retraining is a **ZenML DAG with gated promotion and rollback** — evidenced locally and on kind."
- "Marquez receives OpenLineage events from retraining — optional kind profile."

### Security / ops

- "Mutation endpoints return **403 in demo/cloud mode** — no auth layer, but hard mutation block."
- "CI runs detect-secrets, Bandit, pip-audit, Trivy, and kubeconform on deploy manifests."

### Honesty (use proactively)

- "All demo data is **synthetic seed 42**. No production customer."
- "Cloud profiles are **templates** — I validated offline, activation is manual."
- "kind Kubernetes is **local evidence**, not GKE/EKS operations."

---

## Technical signal bullets

- External sidecar architecture over enterprise open-source (InvenTree)
- Temporal backtest with global LightGBM + statistical baselines + intermittent methods
- Quantile-based inventory policy (safety stock, ROP, EOQ, stockout risk)
- Full local MLOps loop with drift detection, registry, champion/challenger, packaging
- ZenML retraining with Optuna, gated promotion, rollback, OpenLineage emission
- Prometheus metrics + Grafana dashboards + AlertManager end-to-end alert smoke test
- Marquez lineage for retraining job evidence
- Defensive security pipeline + CI scanning (secrets, SAST, deps, container)
- Multi-cloud deploy templates with deployment contract and offline validation
- 154 pytest tests, senior QA evidence collector, `make demo-local` one-command chain

---

## Business impact bullets (honest framing)

- Decision support layer for inventory ops review — ranked reorder and stockout risk
- Accelerates "what needs attention this week" without replacing ERP workflows
- Simulated cost-aware backtest shows quantile policy vs naive baselines (**synthetic only**)
- Deployable read-only API enables technical teams to add AI ops beside existing inventory stack
- Auditable evidence trail (MLflow runs, drift reports, lineage events) for model governance conversations

---

## Stack list

**Languages & tooling:** Python 3.12, uv, Ruff, pytest, Make, GitHub Actions

**ML & data:** LightGBM, StatsForecast, Croston/SBA, Optuna, Pandera, Polars, DVC, Feast

**MLOps:** MLflow, Evidently, ZenML, BentoML, OpenLineage, Marquez

**Serving & API:** FastAPI, uvicorn, Docker

**UI:** Streamlit, Plotly

**Observability:** Prometheus, Grafana, Loki, Tempo, OpenTelemetry, AlertManager

**Infrastructure:** Docker Compose, kind, Kubernetes, Helm

**Cloud (templates):** GCP Cloud Run, AWS ECS Fargate, Azure Container Apps

**Security:** detect-secrets, Bandit, pip-audit, Trivy, Syft (SBOM)

**Base system:** InvenTree (external, unmodified)

---

## What not to overclaim

| Do not say | Say instead |
|------------|-------------|
| "Reduced inventory costs by X%" | "Simulated backtest showed X% vs naive baseline on synthetic data" |
| "Deployed to GCP/AWS/Azure" | "Cloud Run/ECS/Container Apps templates validated offline; activation is manual" |
| "Production MLOps platform" | "Local MLOps loop with retraining evidence on kind" |
| "Real-time InvenTree integration" | "Optional read-only ingestion; default demo uses synthetic data" |
| "Enterprise-grade security" | "Defensive security pipeline + mutation blocking; no production auth yet" |
| "Kubernetes in production" | "Local kind profiles with Helm charts and smoke tests" |

---

## Suggested project links

| Link | URL / path | Status |
|------|------------|--------|
| GitHub repo | https://github.com/dannzapper-cmd/project-3 | Live |
| Case study | `docs/case-study.md` | In repo |
| Architecture | `docs/architecture-final.md` | In repo |
| Demo script | `docs/demo-script.md` | In repo |
| Screenshots | `docs/assets/screenshots/` | In repo |
| Quick demo | `docs/tutorials/quick-demo-walkthrough.md` | In repo |
| PR-12.6 QA evidence | `docs/evidence/PR12_6_SENIOR_QA_USABLE_DEMO.md` | In repo |
| Live Cloud Run demo | `[placeholder]` | Manual activation |
| Demo video | `[placeholder]` | Record from demo script |
| Portfolio page | `[placeholder]` | Future |
