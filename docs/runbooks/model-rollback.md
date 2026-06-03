# Runbook — Model rollback (PR-11A)

InvForge has **two** rollback levers. Use the one that matches what you need to
undo.

## 1) Registry rollback (champion alias) — always available

Reverts the MLflow model-registry **champion** alias to the previous version.
This is the source-of-truth rollback and works without Kubernetes (PR-09).

```bash
# DRY RUN (default; mutates nothing) — shows what would change
make model-rollback

# Execute (moves the champion alias back)
make model-rollback-confirm
```

See `mlops/retraining/rollback.py`. A failed retrain never promotes, so rollback
is mainly for reverting a promotion you no longer want.

## 2) Blue-green Service switch — requires a deployed BentoML image

The BentoML chart templates a blue-green topology: `blue` and `green`
Deployments and **one Service whose selector picks the active color**. Switching
or rolling back is a selector patch — instant, no pod restarts.

> **PR-11A status:** BentoML is **disabled** (no container image exists yet), so
> this switch is a ready-to-use control plane, **not yet operable**. It becomes
> live only after you build and deploy a real BentoML image. Blue-green is
> therefore **not claimed as implemented** in PR-11A. See ADR 002.

### Enable it (after PR-11A)

```bash
make mlops-loop                 # package champion into the local BentoML store
make bento-build                # bentoml build -f deploy/k8s/bentofile.yaml .
make bento-containerize         # -> invforge_demand_forecast:local
make k8s-load-bento             # kind load docker-image

helm upgrade --install invforge deploy/k8s/helm/invforge -n invforge-ai \
  -f deploy/k8s/helm/invforge/values.yaml -f deploy/k8s/helm/invforge/values-local.yaml \
  --set bentoml.enabled=true \
  --set bentoml.versions.green.enabled=true \
  --set bentoml.image.repository=invforge_demand_forecast \
  --set bentoml.image.tag=local
```

### Switch / roll back

```bash
make model-switch-green         # cut traffic to green (v2)
make model-switch-blue          # cut traffic back to blue (v1)
make model-switch-rollback      # alias for switching back to blue (stable)

# Verify which pods the Service targets
kubectl get endpoints invforge-bentoml -n invforge-ai
```

Each target calls `deploy/k8s/scripts/model-switch.sh`, which `kubectl patch`es
the Service selector `invforge.io/model-color`. If the Service is absent (BentoML
disabled) the script exits with a clear error and the build prerequisites.

## Which one do I use?

- **Bad model promoted, want the previous version everywhere** → registry
  rollback (`make model-rollback-confirm`), then redeploy/restart servers.
- **New version deployed alongside old, want to flip live traffic** → blue-green
  switch (`make model-switch-*`).
