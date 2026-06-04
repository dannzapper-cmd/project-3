# Runbook — Manual retraining trigger on Kubernetes (PR-11A)

Run the InvForge retraining pipeline as a one-shot Kubernetes Job, or trigger the
(suspended) CronJob on demand. Uses the **verified** existing command
`python -m mlops.retraining.runner retrain` — the same code path as
`make retrain-smoke`. No new model-serving or training logic is invented.

## Why a separate image

The AI Ops runtime image excludes the heavy `ml`/`retraining` groups (LightGBM,
MLflow, ZenML, Optuna). Retraining therefore uses a **dedicated image**
`invforge-retraining:local`, built from `deploy/k8s/Dockerfile.retraining`. A Job
on the AI Ops image would fail with `ImportError`.

## One-shot Job (recommended)

```bash
# Builds invforge-retraining:local, loads it into kind, and creates the Job
# via Helm (--set retraining.job.enabled=true).
make k8s-retrain

# Follow it
kubectl get jobs,pods -n invforge-ai -l app.kubernetes.io/component=retraining
kubectl logs -n invforge-ai -l app.kubernetes.io/component=retraining -f
```

The Job runs **smoke mode** by default: deterministic, fast, self-contained
(generates synthetic data; no running server needed). Change the mode with
`--set retraining.mode=full` (heavier).

## Trigger the CronJob manually

The CronJob ships **suspended** (`retraining.cronjob.suspend=true`) so nothing
runs unattended. To enable it and/or trigger a run now:

```bash
# Render the CronJob (still suspended)
helm upgrade --install invforge deploy/k8s/helm/invforge -n invforge-ai \
  -f deploy/k8s/helm/invforge/values.yaml -f deploy/k8s/helm/invforge/values-local.yaml \
  --set retraining.cronjob.enabled=true \
  --set retraining.image.repository=invforge-retraining \
  --set retraining.image.tag=local

# Trigger a run on demand without waiting for the schedule
kubectl create job --from=cronjob/invforge-retrain retrain-manual -n invforge-ai
```

To actually let it run on schedule, additionally set
`--set retraining.cronjob.suspend=false` (weekly, Sundays 03:00 by default).

## Fail-safe behaviour

- **`backoffLimit: 0`** — a failed retrain does not retry or loop.
- **No promotion on failure** — the pipeline's quality gate only promotes a
  model when metrics improve; a failed command never moves the champion alias
  (see `mlops/retraining/gate.py`, `rollback.py`).
- Inspect a finished run's summary in the pod logs (status, promoted, metrics).

## Known limitation — ephemeral ZenML state

ZenML uses a local SQLite stack at `.zenml_local/`. Inside a Job this path is
**ephemeral per run** and does not persist between runs. For persistent pipeline
history a PersistentVolumeClaim is required — **deferred to production hardening**.
Smoke/full runs are self-contained, so this does not affect a single run.
