# Runbook — Local Kubernetes startup (PR-11A)

Bring up the InvForge **AI layer** on a local `kind` cluster and deploy the AI
Operations API via Helm. InvenTree is **not** part of this — it stays in Docker
Compose (sidecar architecture). No cloud resources are created.

## Prerequisites

Install these tools (minimum verified versions):

| Tool    | Min version | Install |
|---------|-------------|---------|
| Docker  | 24+         | https://docs.docker.com/get-docker/ |
| kind    | 0.23        | https://kind.sigs.k8s.io/docs/user/quick-start/#installation |
| kubectl | 1.29        | https://kubernetes.io/docs/tasks/tools/ |
| helm    | 3.14        | https://helm.sh/docs/intro/install/ |

Check everything (and get a warning if InvenTree Compose is running):

```bash
make k8s-preflight
```

## Mandatory startup sequence

Run **one heavy workload at a time** on an 8 GB laptop.

```bash
# 1) Stop InvenTree if it is running (avoids OOM). k8s-up also hard-stops if it
#    detects the Compose stack still up.
make docker-down

# 2) Build the AI Operations API image (tag must match Helm values).
make docker-build-ai            # -> invforge-ai-ops:local

# 3) Create the kind cluster (single control-plane node) and load the image.
#    kind has an isolated runtime: host images MUST be loaded or pods ErrImagePull.
make k8s-up

# 4) Deploy the AI layer chart (AI Ops API only by default).
make k8s-deploy

# 5) Inspect.
make k8s-status                 # nodes, namespaces, pods, services

# 6) Smoke: port-forward the API and curl /health (+ /metrics).
make k8s-smoke
```

Tear down when done:

```bash
make k8s-down                   # kind delete cluster --name invforge-local
```

## What gets deployed

- **AI Operations API** Deployment + Service (ClusterIP), with `/health`
  liveness+readiness probes, CPU/memory requests+limits, non-root
  securityContext (uid 10001, read-only root FS), config via ConfigMap, secret
  placeholders via Secret.
- **NetworkPolicy** manifests (see enforcement note below).
- **BentoML** model server: DISABLED template (no image yet).
- **Retraining** Job/CronJob: opt-in templates (separate image).

Access is always via `kubectl port-forward` (ClusterIP), e.g.:

```bash
kubectl port-forward -n invforge-ai svc/invforge-ai-api 8001:8001
curl -fsS http://localhost:8001/health
```

## NetworkPolicy enforcement (kindnet vs Calico)

By default the cluster uses **kindnet, which does NOT enforce NetworkPolicy** —
the manifests are valid and applied but the rules are not active (structural
documentation). For **real enforcement**:

1. In `deploy/k8s/kind-config.yaml`, uncomment `disableDefaultCNI: true`.
2. Recreate the cluster, then install Calico and wait for it:

```bash
make k8s-down && make k8s-up
kubectl apply -f https://raw.githubusercontent.com/projectcalico/calico/v3.28.0/manifests/calico.yaml
kubectl -n kube-system rollout status ds/calico-node --timeout=180s
make k8s-deploy
```

Trade-off: Calico adds memory overhead. On a tight 8 GB budget, keeping kindnet
(structural-only policies) is the documented default. See ADR 002.

## Model/image signing (cosign — groundwork)

`.github/workflows/cosign-model-signing.yml` provides keyless image signing as
**supply-chain groundwork**. It is `workflow_dispatch` only, never a CI gate, and
needs a GHCR image + OIDC permissions to run. A verify-before-deploy admission
gate is deferred to future production hardening. Do not rely on it for PR-11A
or PR-12 validation.

## Troubleshooting

- **Pods `ErrImagePull`/`ImagePullBackOff`**: image not loaded into kind, or
  `imagePullPolicy` is `Always`. Run `make k8s-load-images`; `values-local.yaml`
  pins `IfNotPresent`.
- **`/health` returns 503 locally**: the chart runs the API in `demo` mode so
  `/health` stays 200 without MLOps artifacts. Confirm the ConfigMap has
  `INVFORGE_ENV=demo`.
- **`k8s-up` refuses to run**: InvenTree Compose is still up. `make docker-down`.
