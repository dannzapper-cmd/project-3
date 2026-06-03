# Runbook — Local Kubernetes smoke test (PR-11A)

Verify the AI Operations API is deployed and healthy on the local `kind`
cluster. This checks **only what PR-11A deploys** (the AI API). BentoML and
retraining are opt-in and covered by their own runbooks.

## Prerequisites

The AI layer is deployed (see `docs/runbooks/k8s-startup.md`):

```bash
make k8s-up && make k8s-deploy
```

## One-shot smoke

```bash
make k8s-smoke
```

This runs `deploy/k8s/scripts/smoke.sh`, which:

1. prints `kubectl get nodes`, namespaces, pods, services;
2. waits for the AI API Deployment rollout;
3. port-forwards `svc/invforge-ai-api` to `localhost:8001`;
4. curls `/health` (expects HTTP 200 in demo mode);
5. curls `/metrics` and prints the first lines (Prometheus exposition; the AI
   Ops image ships the `observability` group so `/metrics` is real).

Expected tail:

```
-- GET /health --
{"status": ... , "pr_stage": "PR-07", ...}
-- GET /metrics (first lines) --
# HELP ...
SMOKE OK.
```

## Manual equivalent

```bash
kubectl get pods -n invforge-ai
kubectl rollout status deploy/invforge-ai-api -n invforge-ai --timeout=120s
kubectl port-forward -n invforge-ai svc/invforge-ai-api 8001:8001 &
curl -fsS http://localhost:8001/health ; echo
curl -fsS http://localhost:8001/metrics | head
kill %1   # stop port-forward
```

## Static validation (no cluster required)

```bash
make helm-lint        # helm lint
make helm-template    # render manifests with default + local values
```

## Notes

- `kubectl port-forward` tunnels through the API server and **bypasses
  NetworkPolicy**, so the smoke works regardless of CNI enforcement.
- `/metrics` is part of the deployed image; if it ever returns 503 the
  observability dependency is missing from the image build (it should not be).
