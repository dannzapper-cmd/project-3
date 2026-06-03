# ADR 002 — Kubernetes scope for the AI Operations Layer (PR-11A)

- **Status:** Accepted
- **Date:** 2026-06-03
- **Context PR:** PR-11A — Kubernetes Infrastructure Core + AI Layer Workloads
- **Supersedes/extends:** ADR 001 (PR-10 deploy strategy)

## Context

PR-01–PR-10 delivered the InvForge AI Operations Layer as an external sidecar
over InvenTree: data pipeline, ML baseline, decision intelligence, MLOps loop,
dashboard, observability, defensive security, a local retraining pipeline, and a
deployable runtime image with multi-cloud profiles.

PR-11 (Senior Edition) introduces Kubernetes. To keep scope controlled and
reviewable, PR-11 is split: **PR-11A is the Kubernetes infrastructure core +
AI-layer workloads**; PR-11B adds advanced observability and lineage. This ADR
records the PR-11A decisions and the honest limits of what it ships.

## Decision

### kind, not k3s/GKE/EKS/AKS — and only locally

PR-11A targets **local `kind`** (Kubernetes-in-Docker) with a **single
control-plane node**. kind is the lightest way to get a real, conformant
Kubernetes API on an 8 GB laptop with zero cloud cost and instant teardown
(`kind delete cluster`). k3s is a fine alternative but adds a second toolchain
for no demo benefit here. **No GKE/EKS/AKS/Cloud Run resources are created** —
managed clusters cost money, need accounts/credentials, and are out of scope for
a portfolio PR. Cloud Kubernetes remains documentation-only (ADR 001).

### Only the AI layer goes to Kubernetes

The chart deploys the **AI Operations API** (the PR-10 runtime image) and
templates for the **BentoML model server** and **retraining Job/CronJob**.
Nothing else.

### InvenTree stays outside Kubernetes

InvForge is a **sidecar**. InvenTree (Django + PostgreSQL + cache + worker +
proxy) is a heavy, stateful, security-sensitive system; moving it into kind
would blow the RAM budget, risk coupling InvForge to InvenTree core, and violate
the project's central architecture rule. InvenTree stays in `app/` Docker
Compose, unchanged. **No InvenTree core files are modified in PR-11A.**

### BentoML is templated but DISABLED (no image yet)

The BentoML **entrypoint exists** (`mlops/service.py`:`DemandForecastService`),
but **no container image exists yet**. Containerization is a one-command step
deferred to after PR-11A merge:

```
make mlops-loop          # package champion model into the local BentoML store
make bento-build         # bentoml build -f deploy/k8s/bentofile.yaml .
make bento-containerize  # -> invforge_demand_forecast:local
make k8s-load-bento      # kind load docker-image
helm upgrade ... --set bentoml.enabled=true
```

Therefore the BentoML Deployment/Service templates ship **disabled**
(`bentoml.enabled=false`) with a prominent banner. **Blue-green is NOT claimed as
implemented**: the blue/green deployments + single-Service color selector are
fully templated and there are `make model-switch-*` controls, but they only
become operable once a real image is deployed. We did **not** invent a BentoML
Dockerfile from scratch.

### Retraining uses a SEPARATE image

The AI Ops runtime image deliberately excludes the `ml`/`retraining` dependency
groups (LightGBM, MLflow, ZenML, Optuna) to stay small. A Job using that image
would fail with `ImportError`. So the retraining Job/CronJob use a dedicated
image **`invforge-retraining:local`** built from
`deploy/k8s/Dockerfile.retraining` (`make k8s-retrain-image`). The Job calls the
**verified** existing command `python -m mlops.retraining.runner retrain --mode
smoke` (the same code path as `make retrain-smoke`). It fails safe:
`backoffLimit: 0` (no retry loop) and the pipeline's own quality gate never
promotes a model on failure. **ZenML uses a local SQLite stack
(`.zenml_local/`) that is ephemeral per Job run** — persistent pipeline state
needs a PVC, deferred to PR-11B / production.

### NetworkPolicy: kindnet, structural-only (Option B)

kind's default CNI is **kindnet, which does NOT enforce NetworkPolicy**. We keep
kindnet (lowest RAM for an 8 GB laptop) and ship valid NetworkPolicy manifests
(default-deny ingress, DNS egress, scoped AI-API and BentoML ingress) as
**structural documentation**. They render and apply cleanly but are not
enforced. To get **real enforcement**, set `disableDefaultCNI: true` in
`deploy/k8s/kind-config.yaml` and install Calico (steps in
`docs/runbooks/k8s-startup.md`). We chose Option B over bundling Calico to
respect the RAM budget; the trade-off is documented honestly rather than implied.

### Redis is NOT included

The AI Operations API (`api/`) has **no cache integration** (no Redis in
`pyproject.toml`, Compose, or code). Adding a Redis Deployment would be
decoration. **Redis inference caching is deferred to PR-11B / production
hardening.** This is a deliberate, honest omission.

### Cosign is groundwork, not a gate

`.github/workflows/cosign-model-signing.yml` is **`workflow_dispatch` only**,
not wired into `ci.yml`, and cannot block PR checks. It documents the keyless
(Sigstore) signing path and requires a pushed GHCR image + OIDC permissions to
actually run. Promotion to a real admission gate (verify-before-deploy) is
deferred to PR-11B / production.

### Why PR-11B is deferred

LGTM (Loki/Grafana/Tempo/Mimir), OpenTelemetry Collector, AlertManager, and
OpenLineage/Marquez are each a non-trivial stateful stack. Running them
alongside the AI workloads would exceed the 8 GB budget and balloon this PR. The
`invforge-observability` namespace is created (optionally) as a reserved
placeholder only. Cross-signal observability, alerting, and lineage land in
PR-11B with their own runbooks.

## RAM / cost trade-offs

- **One control-plane node, no workers**: minimum footprint that is still a real
  cluster. Workers add memory pressure for no demo value.
- **Run one heavy thing at a time**: stop InvenTree Compose (`make docker-down`)
  before `make k8s-up`; `k8s-up` hard-stops if Compose is still running.
- **ClusterIP + port-forward**, never LoadBalancer/NodePort: no extra
  controllers, no host-port collisions.
- **`imagePullPolicy: IfNotPresent`** + `kind load docker-image`: images are
  local-only; `Always` would force a doomed registry pull (ErrImagePull).
- **kind over managed clusters**: $0 and instant teardown vs. accounts, IAM,
  state, and standing cost.

## Consequences

- InvForge gains a small, real, reproducible local Kubernetes spine for the AI
  layer: AI Ops API deployable via Helm, probed, resource-bounded, non-root.
- Honest templates mark work that depends on a follow-up step (BentoML image,
  Calico enforcement, retraining PVC, Redis, signing gate).
- No cloud resources, no InvenTree core changes, no committed secrets.
- PR-11B extends this with observability/lineage without re-architecting.
