# InvForge — Case study

**AI Operations Control Tower for inventory and supply chain**

---

## Problem

Inventory teams often rely on fragmented spreadsheets, reactive reorder rules,
and delayed visibility into stockout risk. A traditional inventory system
(InvenTree, ERP, WMS) knows **what is on hand** but not **what will be needed**
over the next reorder cycle — especially for intermittent spare parts and
long-lead-time SKUs.

The gap is not missing data entry; it is missing a **decision layer** that turns
demand history into forecast-informed actions with auditable model health.

## Constraints

- **Do not modify InvenTree core.** Enterprise integrations must be defensible:
  sidecar pattern, REST API consumption, no fork chaos.
- **8 GB laptop development.** Heavy stacks (kind + observability + lineage)
  run sequentially, not concurrently.
- **No fake production claims.** All quantified business metrics are synthetic
  backtest diagnostics unless backed by real production data.
- **Cost-conscious cloud.** Deploy surface is a single read-only API container;
  MLflow, dashboard, and retraining stay local.
- **Portfolio honesty.** Templates and activation guides, not live multi-cloud.

## Architecture decision

**External AI Operations sidecar** over InvenTree:

| Choice | Rationale |
|--------|-----------|
| Sidecar vs fork | Clean integration story; InvenTree remains system of record |
| FastAPI control plane | Small deployable surface; `/health`, `/metrics`, read-only status |
| Synthetic default path | Reproducible demos without private inventory data |
| Streamlit dashboard (local) | Fast artifact visualization; not cloud-deployed |
| kind k8s for Senior Edition | Local evidence for Helm, observability, lineage — not managed cloud |
| Cloud Run as primary profile | Scale-to-zero, low-cost public demo target for read-only API |

See [architecture overview](architecture-final.md) and ADR
[001-deploy-strategy](adr/001-deploy-strategy.md).

## Implementation

InvForge spans 13 incremental PRs (PR-01 through PR-12.6 merged):

1. **Base stack** — InvenTree Docker Compose, repo structure, CI skeleton
2. **Data pipeline** — ingestion, Feast defs, Pandera validation, DVC
3. **ML baseline** — LightGBM global model, StatsForecast, Croston/SBA for intermittent demand
4. **Decision intelligence** — quantile forecasts → safety stock, ROP, EOQ, stockout risk
5. **MLOps loop** — Evidently drift, MLflow registry, champion/challenger, BentoML packaging
6. **Dashboard** — read-only Streamlit control tower
7. **Observability** — `/health`, `/metrics`, local Prometheus/Grafana
8. **Defensive security** — audit pipeline, risk scoring, CI scanning
9. **Retraining** — ZenML DAG, Optuna smoke, gated promotion, rollback
10. **Cloud deploy profiles** — GCP/AWS/Azure templates for read-only API
11. **Senior Edition** — kind Kubernetes AI layer, LGTM observability, Marquez lineage
12. **Full QA audit** — hardening, evidence collector, senior validation

Single-command demo chain: `make demo-local`.

The Streamlit dashboard section **0. How InvForge Works** makes the backend chain
visible: data → validation → forecasting → decision intel → MLOps, plus companion
surfaces (API, observability, lineage). Green status cards mean artifacts exist on
disk — the UI is read-only proof, not the compute layer.

## AI/ML pipeline

**Demand forecasting:**

- Global **LightGBM** with temporal backtest
- **StatsForecast** baselines (AutoETS, SeasonalNaive)
- **Croston/SBA** for intermittent/lumpy SKUs (ADI/CV² classification)
- **p10/p50/p90 quantiles** — not point forecasts alone

**Decision intelligence:**

- Safety stock, reorder point, EOQ from forecast quantiles and lead times
- Stockout risk ranking (backtest-style diagnostic)
- Simulated cost-aware metrics (newsvendor / pinball loss framing)
- Explicit warnings when synthetic improvement is large

**Model cards and explainability:**

- Documented in `docs/model-cards/demand_forecast_baseline.md`
- SHAP and champion/challenger comparison in MLOps artifacts

## MLOps and retraining

- **MLflow 3** — local experiment tracking and model registry
- **Evidently** — drift and data quality reports
- **Champion/challenger** — comparison JSON with manual review gate
- **BentoML** — model packaging (local evidence)
- **ZenML retraining DAG** — Optuna smoke, gated promotion, safe rollback
- **OpenLineage → Marquez** — optional kind profile emits `invforge.retraining` events

Retraining is **local/kind Job evidence**, not a public cloud endpoint.

## Observability and lineage

- API exposes Prometheus metrics and structured health payloads
- Local Docker stack: Prometheus + Grafana (`make observability-up`)
- kind LGTM profile: Loki, Tempo, AlertManager with end-to-end alert smoke test
- Marquez UI for retraining lineage (optional kind profile)
- Tempo/OTel idle until API tracing instrumentation

## Defensive security

- Secrets scanning (detect-secrets baseline), Bandit, pip-audit, Trivy in CI
- CycloneDX SBOM generation (local, gitignored artifact)
- Security audit pipeline with risk scoring on synthetic events
- Mutation endpoints blocked in demo/cloud mode
- WAF/DDoS templates for GCP/AWS/Azure (activation-ready, not live)
- No offensive security tooling

## Deployment readiness

**Deployable today (template activation):**

- Single Docker image → Cloud Run (primary), ECS Fargate, Azure Container Apps
- Read-only API surface per [deployment contract](deployment-contract.md)
- Offline validation: `make deploy-validate` (66 deploy files)

**Not deployed in CI or PR-13.** Cloud profiles require manual credentials.

## Business case

InvForge addresses a practical operations problem:

> Turn inventory events and demand history into forecast-informed decisions,
> risk flags, reorder recommendations, model health checks, and auditable
> operational evidence — **without replacing the core ERP/inventory system.**

**Value proposition (decision support, not magic):**

- Reduce stockout/overstock **risk visibility** for ops review cycles
- Accelerate weekly inventory review with ranked recommendations
- Give technical teams a deployable, observable AI sidecar
- Provide MLOps discipline evidence (drift, registry, retraining gates)

**What we do not claim:** real customer deployments, production ROI, or dollar
savings from synthetic backtests.

## Demo scenario

Concrete SKU story in `examples/demo-scenario/`:

| SKU | Pattern | Ops action |
|-----|---------|------------|
| SKU-A100 | Regular fast mover | Standard ROP, weekly review |
| SKU-B220 | Intermittent spare | Croston/SBA forecast; avoid naive averages |
| SKU-C330 | Rising trend | Reorder soon — stockout risk |
| SKU-D440 | Long lead time (21d) | Safety stock dominates |

Run: `make demo-local` → `make dashboard`.

## Validation evidence

- **PR-12.6 senior QA:** 154 pytest passed, deploy-validate, secrets-scan,
  security-check, demo-local, Docker/kind/observability/lineage smoke tests
- Report: [PR12_6_SENIOR_QA_USABLE_DEMO.md](evidence/PR12_6_SENIOR_QA_USABLE_DEMO.md)
- **PR-13 packaging:** screenshots, case study, portfolio docs (this document)
- GitHub Actions: verify after PR-13 push

## Tradeoffs

| Tradeoff | Choice | Cost |
|----------|--------|------|
| Dashboard local-only | Faster iteration, no cloud artifact sync | Reviewers must run locally for UI |
| No production auth | Mutation blocking only | Public read-only routes unauthenticated |
| Synthetic default | Reproducible, no PII | Not representative of real demand patterns |
| kind vs managed k8s | Local evidence on 8 GB Mac | Not production k8s operations story |
| Scale-to-zero Cloud Run | Low cost | Cold starts on first request |
| Manual cloud activation | No credentials in CI | Reviewer cannot "click deploy" without setup |

## What I would do next in production

1. **Auth and network** — OAuth2/API keys, private VPC, Cloud Armor / WAF live
2. **IaC** — Terraform modules for Cloud Run + Secret Manager + Artifact Registry
3. **Real InvenTree integration** — scheduled ingestion, token rotation, data freshness SLOs
4. **Managed MLOps** — hosted MLflow or Vertex/SageMaker model registry, scheduled retraining CronJob
5. **Production observability** — SLOs, paging, long-term metrics, distributed tracing on API
6. **Feature store** — Feast online serving with Redis; training/serving consistency tests
7. **Cost governance** — budget alerts, autoscaling policies, environment separation

## Interview narrative

**30-second version:**

> I built InvForge — an AI Operations sidecar for inventory. It sits outside
> InvenTree, adds demand forecasting and decision intelligence on synthetic
> data, and ships with MLOps, observability, and cloud-ready deploy templates.
> The deployable surface is a read-only FastAPI service; the dashboard and
> retraining are local evidence. Everything is honest about what's simulated
> vs production-ready.

**Deep-dive prompts I can answer:**

- Why sidecar instead of fork? → Clean enterprise integration, auditable boundary
- How do you handle intermittent demand? → ADI/CV² classification, Croston/SBA
- How do quantiles feed inventory policy? → p90 for safety stock, newsvendor framing
- What's deployable vs local? → Deployment contract, endpoint classification
- How do you prevent mutation in cloud? → `INVFORGE_ALLOW_MUTATIONS=false`, 403 gate
- What did QA prove? → PR-12.6 evidence table, kind alert test, Marquez lineage smoke

**Links:** [README](../README.md) · [demo script](demo-script.md) · [portfolio pack](portfolio-pack.md) · [limitations](limitations.md)
