# Deployment Contract — InvForge AI Operations Layer (PR-10)

This document is the authoritative contract for what PR-10 makes deployable, what
it deliberately keeps local-only, and how the InvenTree **sidecar** architecture
is preserved. It is honest by design: profiles are **activation-ready templates**,
not active cloud deployments.

## 1. What PR-10 deploys

PR-10 makes **only the external AI Operations API** (the FastAPI sidecar in
`api/`, plus the read-only `observability/` health+metrics layer) deployable as a
single container image (repo-root `Dockerfile`). It runs as a stateless,
read-only **demo/cloud** service.

## 2. What PR-10 does NOT deploy

- **InvenTree core** (the base inventory system) — stays external/unchanged. The
  sidecar pattern means InvForge talks to InvenTree over its REST API; PR-10 does
  not containerize, fork, or deploy InvenTree.
- **MLflow** local tracking/registry UI/server (`mlruns/`).
- **ZenML** local stack/server.
- **Retraining** mutation path as a public endpoint.
- **Streamlit dashboard** — separate Cloud Run profile in PR-15
  (`Dockerfile.dashboard`); read-only with bundled synthetic fixtures and
  optional reviewer login gate. Not in the API container image.
- **Security-sensitive** operations / audit-write paths.
- Large/ephemeral local file-store artifacts (`mlruns/`, `artifacts/`).
- **Kubernetes / Helm / Senior Edition** — outside PR-10. PR-11A/11B add local
  kind profiles for the AI layer, observability, and lineage; cloud Kubernetes
  remains out of scope.

## 3. Deployability analysis (DA-1)

1. **Can the AI Operations API start without local `mlruns/`, `artifacts/`, or
   retraining state?** **Yes.** The API imports no ML/retraining code at startup
   and the health builder degrades gracefully (it reads only artifact
   existence/mtime and never raises). To keep provider health checks green on a
   fresh container with no artifacts, **demo/cloud mode returns HTTP 200 from
   `/health`** while still reporting true artifact status in the payload. → The
   service is deployable with no bundled artifacts.
2. **Can the dashboard start without live ML inference calls?** **Yes** for
   cloud demo mode: PR-15 bundles lightweight committed fixtures under
   `dashboard/demo_fixtures/` and never trains on cold start. Local mode still
   reads workspace artifacts from `make reviewer-demo`.
3. **Endpoint classification** — see §4.
4. **InvenTree is not part of the PR-10 cloud deploy surface.** Not
   containerized or deployed here.

No stop condition was triggered: the API starts cleanly without mutable local
state, the runtime image stays small (core + observability deps only), and no
real credentials or live resources are needed.

## 4. Endpoint classification (SAFE vs UNSAFE)

| Method & path | Class | Public in cloud/demo? | Justification |
|---------------|-------|-----------------------|---------------|
| `GET /health` | **SAFE** | Yes | Read-only health/status; no paths/secrets/PII (PR-07 contract). |
| `GET /metrics` | **SAFE** | Yes | Read-only Prometheus metrics; allowlisted, low-cardinality. |
| `GET /v1/inventory/status` | **SAFE** | Yes | Read-only; reports config booleans + local data summary; never returns token/password values. |
| `GET /v1/data/summary` | **SAFE** | Yes | Read-only summary of local processed data. |
| `POST /v1/ingest/inventree` | **UNSAFE** | **No (blocked)** | Reaches out to InvenTree and **writes** raw + processed snapshots to the data dir (mutation + external dependency). |

**Enforcement:** the only UNSAFE endpoint is gated by `INVFORGE_ALLOW_MUTATIONS`.
In `demo`/`cloud` mode it defaults to **`false`** and the endpoint returns
**HTTP 403** without performing any work or leaking secrets. There is no auth
gate in PR-10, so mutation-blocking is the hard default for any cloud surface.
The deploy smoke script (`scripts/deploy_smoke.py`) refuses, in code, to call any
path containing `retrain`, `rollback`, `promote`, `register`, `delete`, `audit`,
`scan`, or `ingest`.

Endpoints exposing **MLflow UI**, **ZenML UI**, or **retraining mutation** do not
exist in the deployable API and are **local-only** by construction (run via the
`make` targets, not the FastAPI app).

## 5. Runtime modes

Configured via env vars (reusing the existing `api/config.py` `Settings`
pattern — no new config framework):

| Var | Values | Default (local/ci) | Default (demo/cloud) |
|-----|--------|--------------------|----------------------|
| `INVFORGE_ENV` | `local` \| `ci` \| `demo` \| `cloud` | `local` | — |
| `INVFORGE_DEMO_MODE` | bool | `false` | `true` |
| `INVFORGE_ALLOW_MUTATIONS` | bool | `true` | **`false`** |
| `PORT` | int | (8001) | injected by provider |
| `LOG_LEVEL` | string | `INFO` | `INFO` |

- **local / ci** preserve the historical developer behavior (mutations allowed,
  strict 503-on-empty health). Existing tests and local workflows are unchanged.
- **demo / cloud** are read-only by default, block mutations, and keep `/health`
  at 200 so provider probes pass on a fresh container.

Defaults are derived from `INVFORGE_ENV`; each flag can be explicitly overridden.
**Never set `INVFORGE_ALLOW_MUTATIONS=true` on a public deployment.**

## 6. Operations that remain local-only

- The Streamlit dashboard (`make dashboard`) — also deployable read-only via
  `Dockerfile.dashboard` (PR-15) with bundled demo fixtures.
- Training / decision intelligence / MLOps loop / retraining (`make train-ml`,
  `make mlops-loop`, `make retrain*`).
- MLflow tracking/registry and ZenML stack (local SQLite/file stores).
- Security pipeline / audit (`make security-audit`).
- InvenTree base stack (`make docker-up`).

These rely on mutable local state and/or heavy dependencies that are
intentionally excluded from the runtime image.

## 7. How the sidecar architecture is preserved

InvenTree core is never modified, forked, or deployed by PR-10. The deployable
unit is strictly the external AI layer, which integrates with InvenTree only
through its existing REST API (and only when explicitly configured + mutations
enabled — disabled by default in cloud mode). No `app/` (InvenTree base stack)
files are changed.

## 8. Which services are safe for public/demo deployment

Public/demo-deployable: the AI Operations API running in `cloud`/`demo` mode
(read-only SAFE endpoints, mutations blocked, health 200). The Streamlit
dashboard (PR-15) is deployable separately with bundled synthetic fixtures and
a reviewer login gate — no ML training on cold start.

Not publicly deployed in PR-10: InvenTree, MLflow server, ZenML server, the
retraining mutation path, security-sensitive operations, and large local
artifact stores.

## 9. PR-10 vs PR-11 scope

### Implemented in PR-10

- Deployment contract (this document) + deployment security + SLA monitoring docs.
- GCP **Cloud Run** profile (template + docs) — primary target.
- AWS **ECS/Fargate** profile (template + docs).
- Azure **Container Apps** profile (template + docs).
- Docker runtime image for the AI Operations Layer + `.dockerignore`.
- Deploy smoke script (read-only) + `make deploy-smoke`.
- Cloud/demo **safety gate** (mutation-blocking) with tests.
- WAF/DDoS **profile templates** (Cloud Armor / AWS WAF / Front Door WAF).
- Cost and teardown docs.
- Deployment ADR.
- CI template validation (no cloud resources) + opt-in SLA monitoring workflow.

### Profile / template only (not actively deployed)

- GCP, AWS, Azure deploy templates require **manual activation** with real
  credentials. WAF templates require a provider account + public entrypoint.
- No live GCP/AWS/Azure resources are created or maintained by InvForge or CI.

### Implemented after PR-10 (PR-11A / PR-11B, local-only)

- Local kind + Helm path for the AI Operations Layer (`make k8s-*`).
- Kubernetes AI API Deployment/Service plus opt-in retraining Job/CronJob
  templates.
- Optional observability profile (`make obs-k8s-*`) with Prometheus, Grafana,
  Loki, Tempo, AlertManager, OTel receivers, and webhook alert testing.
- Optional lineage profile (`make lineage-*`) with env-gated OpenLineage emission
  and local Marquez.
- Model signing groundwork (`workflow_dispatch` only; not a CI/deploy gate).
- Blue/green BentoML manifests and switch scripts are templated but disabled
  until a real Bento image is built.

### Still deferred to production hardening / future work

- Redis inference cache.
- Strict Cosign verify-before-deploy or admission policy.
- Active cloud Kubernetes (GKE/EKS/AKS), WAF, production RBAC, and formal SLA.

### Deferred to production hardening (beyond PR-10/PR-11)

- Full Terraform/CDK/Bicep IaC and remote state.
- Active multi-region, active WAF deployment, production RBAC, formal SLA.

## 10. What would be required to make this production-grade

Beyond portfolio/demo use: real provider accounts + least-privilege IAM, a
secret store wired to live credentials, a public entrypoint with **active WAF**,
IaC with remote state and CI/CD promotion, authn/authz in front of any
non-read-only endpoint, autoscaling/SLO budgets and alerting, and a managed
backing store for any persisted artifacts.
