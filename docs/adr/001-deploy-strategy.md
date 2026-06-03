# ADR 001 — Deployment strategy for the AI Operations Layer (PR-10)

- **Status:** Accepted
- **Date:** 2026-06-03
- **Context PR:** PR-10 — Deploy + Multi-cloud Profiles

## Context

InvForge is an external AI/MLOps sidecar over InvenTree. PR-01–PR-09 delivered
the data pipeline, ML baseline, decision intelligence, MLOps loop, dashboard,
observability, defensive security, and a local retraining pipeline. PR-10 must
make InvForge **deployable, cloud-ready, portable, cost-aware, and auditable**
without implementing Kubernetes/Senior Edition (PR-11) and without creating live
cloud resources or requiring real credentials for validation.

## Decision

### Deploy only the external AI Operations Layer

PR-10 packages and deploys **only** the FastAPI AI Operations API (`api/`) plus
the read-only `observability/` health+metrics layer, as a single container
image. This is the minimal, honest, low-cost surface that demonstrates
cloud-readiness while preserving the sidecar architecture.

### InvenTree core is not deployed as a full production system

The sidecar pattern requires InvenTree to remain external and unchanged.
Containerizing/deploying InvenTree (DB, cache, worker, proxy) would be a heavy,
stateful, security-sensitive production deployment out of scope for a
portfolio/demo PR — and would risk coupling InvForge to InvenTree core. InvenTree
is therefore explicitly **not** part of the PR-10 cloud surface.

### Google Cloud Run is the primary target

Cloud Run is fully managed, supports **scale-to-zero** (near-$0 idle cost),
injects `PORT`, and deploys a single container with minimal ceremony — an
excellent fit for a read-only demo API. It became the primary profile.

### AWS profile uses ECS/Fargate, not App Runner

AWS **App Runner is no longer open to new customers**, so it is unsuitable as the
recommended path. **ECS on Fargate** is the documented AWS container target: a
valid task definition template, WAF template, and teardown script — enough to
activate manually, without provisioning a VPC/ALB/IAM for the user.

### Azure profile uses Container Apps

Azure **Container Apps** is the serverless-container analogue of Cloud Run
(scale-to-zero, simple YAML spec). **AKS/Kubernetes is deferred to PR-11.**

### Not Kubernetes yet

Kubernetes (kind/k3s, Helm, CronJob, LGTM) is the explicit scope of **PR-11
Senior Edition**. Adding it now would bloat PR-10 and duplicate PR-11. The local
Kubernetes path in PR-11 can run **without active cloud clusters**.

### Not Terraform/CDK/Bicep yet

> Full Terraform/CDK/Bicep IaC is intentionally **deferred to production
> hardening after PR-10/PR-11** because active multi-cloud infrastructure
> requires accounts, credentials, state management, and cost controls.

PR-10 ships cloud-native service templates, shell deploy/teardown examples, env
examples, WAF profile templates, validation scripts, and runbooks instead.

### Production-hardening hooks, cost-safe and non-live

PR-10 implements **repo-level mechanisms** that make hardening features activable
later without creating resources: a cloud/demo **safety gate** (mutations blocked
by default, with tests), read-only **smoke/SLA** hooks (graceful skip when no URL
is configured), and **WAF/DDoS profile templates** for all three providers.

## Cost / security trade-offs

- **Scale-to-zero** (Cloud Run / Container Apps) trades cold-start latency for
  near-$0 idle cost. Fargate has no scale-to-zero; the profile documents pausing
  via `desiredCount: 0`.
- **Read-only by default** removes the main attack surface (mutation endpoints)
  for a public demo; live ingestion requires explicitly enabling mutations and
  wiring secrets — discouraged for public surfaces.
- **WAF is a template, not active**, because activation needs a load
  balancer/Front Door and a provider account; honest docs say so.
- Cost figures are **hedged examples**, never guarantees (see
  `docs/costs/deployment-costs.md`).

## How PR-11 extends this

PR-11 adds Kubernetes manifests (kind/k3s), a Helm chart, a Kubernetes CronJob
for retraining, the LGTM observability stack, model signing, blue/green/canary
deploys, and a Redis inference cache — building on PR-10's container image,
contract, and safety gate.

## What would make this production-grade (beyond demo)

Real provider accounts with least-privilege IAM, a secret store wired to live
credentials, a public entrypoint with **active WAF/DDoS**, IaC with remote state
and CI/CD promotion, authn/authz in front of any non-read-only endpoint,
autoscaling with SLO/error budgets and alerting, and a managed backing store for
any persisted artifacts.

## Consequences

- InvForge gains a documented, reproducible, multi-cloud deploy story with a
  small runtime image and a safe-by-default public surface.
- No live cloud resources are created; no credentials are needed to validate.
- Activation is a manual, well-documented step per provider.
