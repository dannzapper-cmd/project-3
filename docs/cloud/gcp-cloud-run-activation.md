# GCP Cloud Run activation — API + Dashboard

Activation-ready deploy profiles for the **read-only** InvForge cloud demo.

## What gets deployed

| Service | Image | Surface |
|---------|-------|---------|
| `invforge-ai-demo` (API) | `Dockerfile` | FastAPI read-only API |
| `invforge-dashboard-demo` (dashboard) | `Dockerfile.dashboard` | Streamlit read-only dashboard |

**Not deployed:** InvenTree, MLflow, ZenML, databases, Kubernetes, mutation endpoints.

## Prerequisites

- GCP project with billing enabled
- `gcloud auth login`
- APIs: Cloud Run, Artifact Registry
- Docker

```bash
export PROJECT_ID=your-gcp-project-id
export REGION=us-central1
```

## 1. API (existing profile)

```bash
export SERVICE_NAME=invforge-ai-demo
export IMAGE_URI="${REGION}-docker.pkg.dev/${PROJECT_ID}/invforge/ai-ops:latest"
./deploy/gcp/deploy.example.sh
```

Verified live API: https://invforge-ai-demo-lwcelvo7ya-uc.a.run.app/docs

## 2. Dashboard (PR-15)

```bash
export DASHBOARD_SERVICE_NAME=invforge-dashboard-demo
export DASHBOARD_IMAGE_URI="${REGION}-docker.pkg.dev/${PROJECT_ID}/invforge/dashboard:latest"
export API_BASE_URL=https://invforge-ai-demo-lwcelvo7ya-uc.a.run.app
export INVFORGE_DEMO_PASSWORD='choose-a-demo-password'  # reviewer gate only
./deploy/gcp/dashboard.deploy.example.sh
```

LIVE_DASHBOARD_URL=https://invforge-dashboard-demo-lwcelvo7ya-uc.a.run.app

## Smoke checks

```bash
URL=$(gcloud run services describe invforge-dashboard-demo \
  --region $REGION --project $PROJECT_ID --format='value(status.url)')

curl -fsS "$URL/_stcore/health"
curl -fsS "$URL/" | grep -i "Reviewer Demo"
# Log in via browser with reviewer / $INVFORGE_DEMO_PASSWORD
```

## Teardown

```bash
./deploy/gcp/dashboard.teardown.example.sh
./deploy/gcp/teardown.example.sh   # API
```

## Cost notes

- `minScale: 0` on both services — scale to zero when idle
- Charges possible for requests, CPU time, image storage, egress
- Verify current GCP free tier / pricing before deploying

See [`deploy/gcp/README.md`](../../deploy/gcp/README.md) and [`costs/deployment-costs.md`](../costs/deployment-costs.md).
