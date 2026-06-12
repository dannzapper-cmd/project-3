# InvForge — Limitations and honest tradeoffs

This document states what InvForge **does not** claim and where the current
implementation stops. Use it alongside the [deployment contract](deployment-contract.md)
and [PR-12.6 senior QA report](evidence/PR12_6_SENIOR_QA_USABLE_DEMO.md).

## Data and business claims

- **Synthetic data by default.** The demo pipeline uses deterministic synthetic
  inventory CSVs (seed 42). No real customer inventory, ERP data, or production
  ROI is included unless you explicitly configure live InvenTree ingestion.
- **No production savings claims.** Decision-intelligence cost metrics are
  **simulated backtest diagnostics** on synthetic data. Do not cite dollar savings,
  stockout reduction percentages, or customer outcomes as real-world results.
- **No real customer use.** InvForge is a portfolio / reference implementation,
  not a deployed product with paying users.

## Architecture boundaries

- **InvenTree core is unchanged.** InvForge is an external sidecar. It does not
  fork, patch, or vendor InvenTree.
- **Sidecar, not replacement.** InvForge augments inventory operations with
  forecast-informed decision support; it does not replace the ERP/inventory
  system of record.

## Deployable surface vs local-only

| Component | Local/dev | Cloud-deployable |
|-----------|-----------|------------------|
| AI Operations API (`/health`, `/metrics`, read-only status) | Yes | **Yes** (primary public surface) |
| Streamlit dashboard | Yes | **No** — requires local artifacts |
| MLflow / ZenML / retraining UI | Yes | **No** — local tooling only |
| InvenTree base stack | Yes (Docker Compose) | **No** — external system |
| Prometheus + Grafana (Docker) | Yes | **No** — local/dev stack |
| kind Kubernetes AI layer | Yes | **No** — local kind, not managed cloud k8s |
| Marquez lineage (kind profile) | Yes | **No** — optional local profile |

## Cloud and multi-cloud

- **One live Cloud Run demo (PR-14).** A read-only AI Operations API is deployed
  at `invforge-ai-demo` in `us-central1` — not production. AWS ECS/Fargate and
  Azure Container Apps remain **activation-ready templates** only.
- **Not live multi-cloud.** Only the GCP read-only API demo is live; dashboard,
  InvenTree, MLflow, ZenML, retraining, and managed Kubernetes are not deployed.
- **Cloud profiles require manual activation** with your own credentials, billing,
  and cost acceptance. See [cloud activation guides](cloud/).
- **No Terraform / full IaC** in the current scope. Production hardening would
  add IaC, secrets management, and environment promotion.

## Security and auth

- **No production auth layer** on the deployable API. Mutation endpoints are
  **blocked** in demo/cloud mode (`INVFORGE_ALLOW_MUTATIONS=false`), but there
  is no OAuth, API keys, or RBAC on read-only routes.
- **Defensive security only** — audit logging, risk scoring, secrets scanning
  in CI. No offensive security tooling.
- **WAF/DDoS templates** (Cloud Armor, AWS WAF, Azure Front Door) are documented
  but not active until manually deployed.

## MLOps and model serving

- **No managed MLflow or ZenML.** Tracking and retraining run locally or in
  optional kind jobs; there is no hosted experiment platform.
- **BentoML blue/green on k8s** is templated but disabled until a real Bento
  image is built and loaded.
- **Foundation-model benchmarks** and advanced deep-learning paths are documented
  as Senior Edition scope; not all are implemented with live evidence.

## Observability and lineage

- **Local/dev observability only** for the Docker Prometheus/Grafana stack.
- **Tempo/OTel backends** deploy in the optional k8s observability profile but
  remain idle until API tracing is instrumented.
- **OpenLineage/Marquez** is env-gated and optional; not a production lineage
  platform.

## Kubernetes

- **kind is local, not managed cloud k8s.** PR-11A/11B profiles run on a local
  kind cluster for evidence and smoke tests. This is not GKE/EKS/AKS.
- **8 GB RAM constraint.** Heavy profiles (AI + observability + lineage) should
  run sequentially, not concurrently, on low-memory machines.

## Future production hardening

What a production deployment would add (out of current scope):

- Managed auth (OAuth2/API keys) and network policies
- Full IaC (Terraform/Bicep/CDK) with environment promotion
- Managed MLflow/model registry and scheduled retraining
- Real InvenTree integration with secret rotation
- SLOs, paging, on-call runbooks, and long-term metrics retention
- Penetration testing and formal threat modeling beyond STRIDE checklist
- Cost governance and autoscaling policies per environment
