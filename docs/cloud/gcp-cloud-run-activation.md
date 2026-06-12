# GCP Cloud Run — activation guide

> **PR-14 status:** A **live read-only demo** is deployed as `invforge-ai-demo` in
> `us-central1`. See [PR14 evidence](../evidence/PR14_CLOUD_RUN_LIVE_DEMO.md).
> This is not production.

Cloud Run is the **preferred low-cost public demo target** for the InvForge
read-only AI Operations API.

## What gets deployed

Only the **AI Operations API** container (repo-root `Dockerfile`):

| Endpoint | Public? |
|----------|---------|
| `GET /health` | Yes (read-only) |
| `GET /metrics` | Yes (read-only) |
| `GET /v1/inventory/status` | Yes (read-only) |
| `GET /v1/data/summary` | Yes (read-only) |
| `POST /v1/ingest/inventree` | **Blocked** (`INVFORGE_ALLOW_MUTATIONS=false`) |

InvenTree, MLflow, ZenML, dashboard, and retraining are **not** deployed.
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
| `SERVICE_NAME` | Yes | e.g. `invforge-ai-ops` |
| `IMAGE_URI` | Yes | Artifact Registry URI |

Container env (set in template):

| Var | Value | Notes |
|-----|-------|-------|
| `INVFORGE_ENV` | `cloud` | Read-only cloud mode |
| `INVFORGE_DEMO_MODE` | `true` | `/health` stays 200 without local artifacts |
| `INVFORGE_ALLOW_MUTATIONS` | `false` | **Never true on public service** |
| `LOG_LEVEL` | `INFO` | |

## Build and push

```bash
export PROJECT_ID=your-gcp-project-id
export REGION=us-central1
export SERVICE_NAME=invforge-ai-ops
export IMAGE_URI="${REGION}-docker.pkg.dev/${PROJECT_ID}/invforge/ai-ops:latest"

gcloud artifacts repositories create invforge \
  --repository-format=docker --location="${REGION}" --project "${PROJECT_ID}"
gcloud auth configure-docker "${REGION}-docker.pkg.dev"

docker build -t "${IMAGE_URI}" .
docker push "${IMAGE_URI}"
```

## Deploy

```bash
./deploy/gcp/deploy.example.sh
```

Uses `deploy/gcp/service.template.yaml`. Grants public `run.invoker` for read-only
demo (comment out IAM step for private access).

## Smoke test

```bash
URL=$(gcloud run services describe "${SERVICE_NAME}" \
  --region "${REGION}" --project "${PROJECT_ID}" --format='value(status.url)')
python scripts/deploy_smoke.py --base-url "${URL}"
```

Expected: `/health` 200, `/metrics` 200, read-only status endpoints OK, mutation
endpoints not called.

## Teardown

```bash
export IMAGE_URI="..."   # optional — delete image too
./deploy/gcp/teardown.example.sh
```

Also review Artifact Registry, Secret Manager, and any Cloud Armor / load
balancer resources.

## Cost warning

- `minScale: 0` → scale to zero when idle; cold starts on first request
- Charges apply for: request/CPU/memory time, Artifact Registry storage, egress, logs
- Low-traffic demo may stay near free-tier depending on account eligibility
- **Verify current GCP pricing before deploying**

## Secret handling

- Never inline tokens in `service.template.yaml`
- Use Secret Manager + `secretKeyRef` for `INVENTREE_API_TOKEN` if enabling ingestion
- Default read-only demo needs **no secrets**

## Source of truth

Detailed reference: [deploy/gcp/README.md](../../deploy/gcp/README.md)

## Live demo (PR-14)

| Field | Value |
|-------|-------|
| Service | `invforge-ai-demo` |
| Region | `us-central1` |
| URL | https://invforge-ai-demo-289428962093.us-central1.run.app |

Smoke: `SERVICE_URL=<url> bash scripts/cloud_run_smoke.sh`

Teardown: `gcloud run services delete invforge-ai-demo --region us-central1`
