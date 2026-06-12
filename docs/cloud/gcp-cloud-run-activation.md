# GCP Cloud Run activation — API + Dashboard

> **PR-14 status:** A **live read-only API demo** is deployed as `invforge-ai-demo` in
> `us-central1`. **PR-15** adds a live read-only Streamlit dashboard at
> `invforge-dashboard-demo`. See [PR14/PR15 evidence](../evidence/PR14_CLOUD_RUN_LIVE_DEMO.md).
> This is not production.

Activation-ready deploy profiles for the **read-only** InvForge cloud demo.

## What gets deployed

| Service | Image | Surface |
|---------|-------|---------|
| `invforge-ai-demo` (API) | `Dockerfile` | FastAPI read-only API |
| `invforge-dashboard-demo` (dashboard) | `Dockerfile.dashboard` | Streamlit read-only dashboard |

**API endpoints (public read-only):**

| Endpoint | Public? |
|----------|---------|
| `GET /health` | Yes (read-only) |
| `GET /metrics` | Yes (read-only) |
| `GET /v1/inventory/status` | Yes (read-only) |
| `GET /v1/data/summary` | Yes (read-only) |
| `POST /v1/ingest/inventree` | **Blocked** (`INVFORGE_ALLOW_MUTATIONS=false`) |

**Not deployed:** InvenTree, MLflow, ZenML, databases, Kubernetes, mutation endpoints.

See [deployment contract](../deployment-contract.md).

## Prerequisites

- GCP project with billing enabled
- `gcloud` CLI authenticated (`gcloud auth login`)
- APIs enabled: Cloud Run, Artifact Registry
- Docker for local image build/push
- Optional: Secret Manager (only if enabling live InvenTree ingestion)

## Environment variables

Copy and edit (do **not** commit):

```bash
cp deploy/gcp/env.example deploy/gcp/.env
# Edit: PROJECT_ID, REGION, SERVICE_NAME
```

| Variable | Required | Notes |
|----------|----------|-------|
| `PROJECT_ID` | Yes | Your GCP project |
| `REGION` | Yes | e.g. `us-central1` |
| `SERVICE_NAME` | Yes | e.g. `invforge-ai-demo` |
| `IMAGE_URI` | Yes | Artifact Registry URI |

Container env (API template):

| Var | Value | Notes |
|-----|-------|-------|
| `INVFORGE_ENV` | `cloud` | Read-only cloud mode |
| `INVFORGE_DEMO_MODE` | `true` | `/health` stays 200 without local artifacts |
| `INVFORGE_ALLOW_MUTATIONS` | `false` | **Never true on public service** |
| `LOG_LEVEL` | `INFO` | |

## 1. API deploy

```bash
export PROJECT_ID=your-gcp-project-id
export REGION=us-central1
export SERVICE_NAME=invforge-ai-demo
export IMAGE_URI="${REGION}-docker.pkg.dev/${PROJECT_ID}/invforge/ai-ops:latest"

gcloud artifacts repositories create invforge \
  --repository-format=docker --location="${REGION}" --project "${PROJECT_ID}" || true
gcloud auth configure-docker "${REGION}-docker.pkg.dev"

docker build -t "${IMAGE_URI}" .
docker push "${IMAGE_URI}"

./deploy/gcp/deploy.example.sh
```

Verified live API: https://invforge-ai-demo-lwcelvo7ya-uc.a.run.app/docs

### API smoke test

```bash
URL=$(gcloud run services describe "${SERVICE_NAME}" \
  --region "${REGION}" --project "${PROJECT_ID}" --format='value(status.url)')
python scripts/deploy_smoke.py --base-url "${URL}"
```

Expected: `/health` 200, `/metrics` 200, read-only status endpoints OK, mutation
endpoints not called.

## 2. Dashboard deploy (PR-15)

```bash
export DASHBOARD_SERVICE_NAME=invforge-dashboard-demo
export DASHBOARD_IMAGE_URI="${REGION}-docker.pkg.dev/${PROJECT_ID}/invforge/dashboard:latest"
export API_BASE_URL=https://invforge-ai-demo-lwcelvo7ya-uc.a.run.app
export INVFORGE_DEMO_PASSWORD='choose-a-demo-password'  # reviewer gate only
./deploy/gcp/dashboard.deploy.example.sh
```

LIVE_DASHBOARD_URL=https://invforge-dashboard-demo-lwcelvo7ya-uc.a.run.app

### Dashboard smoke checks

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
export IMAGE_URI="..."   # optional — delete API image too
./deploy/gcp/teardown.example.sh
```

Also review Artifact Registry, Secret Manager, and any Cloud Armor / load
balancer resources.

## Cost warning

- `minScale: 0` / `min-instances: 0` → scale to zero when idle; cold starts on first request
- `max-instances: 1` caps burst cost on the live demo service
- Charges apply for: request/CPU/memory time, Artifact Registry storage, egress, logs
- Low-traffic demo may stay near free-tier depending on account eligibility
- **No GKE, VM, managed DB, Redis, or load balancer** in the default Cloud Run profile
- Keep a live demo **only during job-search**; run teardown when no longer needed
- **Verify current GCP pricing before deploying**

## Secret handling

- Never inline tokens in `service.template.yaml`
- Use Secret Manager + `secretKeyRef` for `INVENTREE_API_TOKEN` if enabling ingestion
- Default read-only demo needs **no secrets**

## Source of truth

Detailed reference: [deploy/gcp/README.md](../../deploy/gcp/README.md) · [costs](../costs/deployment-costs.md)

## Live demo (verified)

| Field | API | Dashboard |
|-------|-----|-----------|
| Service | `invforge-ai-demo` | `invforge-dashboard-demo` |
| Region | `us-central1` | `us-central1` |
| URL | https://invforge-ai-demo-lwcelvo7ya-uc.a.run.app | https://invforge-dashboard-demo-lwcelvo7ya-uc.a.run.app |
| Auth | Public read-only | `reviewer` / `invforge-demo` (reviewer gate) |

Smoke: `SERVICE_URL=<api-url> bash scripts/cloud_run_smoke.sh`
