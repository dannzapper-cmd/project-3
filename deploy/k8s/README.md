# InvForge — Local Kubernetes (PR-11A)

Kubernetes infrastructure core for the InvForge **AI Operations Layer only**,
running on local [`kind`](https://kind.sigs.k8s.io/). InvenTree core stays in
`app/` Docker Compose and is **never** deployed here (sidecar architecture). No
cloud resources are created.

## Layout

```
deploy/k8s/
  kind-config.yaml          # single control-plane node; kindnet by default
  Dockerfile.retraining     # isolated image with ml+retraining groups (Job/CronJob)
  bentofile.yaml            # BentoML build spec (groundwork; build deferred)
  helm/invforge/            # Helm chart for the AI layer
    Chart.yaml
    values.yaml             # defaults (8 GB-friendly)
    values-local.yaml       # kind overrides: IfNotPresent + ClusterIP (required)
    templates/              # namespace, configmap, secret, AI API deploy/svc,
                            # bentoml (disabled), networkpolicy, retraining
                            # job/cronjob, NOTES.txt
  scripts/
    preflight.sh            # tool + RAM-safety checks
    smoke.sh                # port-forward + curl /health + /metrics
    model-switch.sh         # blue-green Service selector switch
```

## Quick start

```bash
make docker-down            # stop InvenTree (one heavy workload at a time)
make docker-build-ai        # build invforge-ai-ops:local
make k8s-up                 # create kind cluster + load image
make k8s-deploy             # helm upgrade --install (AI Ops API)
make k8s-smoke              # port-forward + curl /health (+ /metrics)
make k8s-down               # delete the cluster
```

Static validation (no cluster): `make helm-lint`, `make helm-template`.

## What is shipped vs deferred

| Item | PR-11A status |
|------|---------------|
| AI Operations API (Deployment+Service, probes, limits, non-root) | **Implemented** |
| ConfigMap + Secret (placeholders only) | **Implemented** |
| NetworkPolicy manifests | **Structural** (kindnet does not enforce; Calico optional) |
| Retraining Job + CronJob (separate image, verified command) | **Implemented (opt-in)** |
| BentoML model server + blue-green | **Templated but DISABLED** (no image yet) |
| Redis inference cache | **Deferred to PR-11B** (no cache in API) |
| Cosign signing | **Groundwork** (workflow_dispatch, non-blocking) |
| LGTM / OTel Collector / AlertManager / OpenLineage / Marquez | **Deferred to PR-11B** |

See `docs/adr/002-pr11a-kubernetes-scope.md` and the runbooks under
`docs/runbooks/k8s-*.md`.
