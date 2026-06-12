# PR-14 — Live Cloud Run demo (read-only AI Operations API)

Date: 2026-06-12  
Repo: `/Users/danny/project-3-clean`  
Branch: `cursor/pr14-live-cloud-run-demo`  
Label: **Live Cloud Run demo of the read-only AI Operations API** — not production.

## Summary

A real Google Cloud Run service exposes only the read-only InvForge AI Operations
API container. Dashboard, MLflow, ZenML, InvenTree core, retraining, and
Kubernetes profiles remain **local-only**.

## Deployment

| Field | Value |
|-------|-------|
| Service name | `invforge-ai-demo` |
| Region | `us-central1` |
| Project ID | `gen-lang-client-0873976301` |
| Service URL | https://invforge-ai-demo-289428962093.us-central1.run.app |

### Deploy commands used

Cloud Build + image deploy (Artifact Registry repo `cloud-run-source-deploy`
already existed from an interrupted `--source` attempt):

```bash
export PROJECT_ID="gen-lang-client-0873976301"
export REGION="us-central1"
export IMAGE="us-central1-docker.pkg.dev/${PROJECT_ID}/cloud-run-source-deploy/invforge-ai-demo:latest"

gcloud builds submit --tag "$IMAGE" --project "$PROJECT_ID" .

gcloud run deploy invforge-ai-demo \
  --image "$IMAGE" \
  --region "$REGION" \
  --project "$PROJECT_ID" \
  --allow-unauthenticated \
  --set-env-vars INVFORGE_ENV=cloud,INVFORGE_DEMO_MODE=true,INVFORGE_ALLOW_MUTATIONS=false,LOG_LEVEL=INFO \
  --max-instances 1 \
  --min-instances 0 \
  --memory 512Mi \
  --cpu 1
```

### Container environment

| Variable | Value |
|----------|-------|
| `INVFORGE_ENV` | `cloud` |
| `INVFORGE_DEMO_MODE` | `true` |
| `INVFORGE_ALLOW_MUTATIONS` | `false` |
| `LOG_LEVEL` | `INFO` |

No secrets, tokens, or credentials were committed or required.

### Cost controls

- `min-instances`: 0 (scale to zero)
- `max-instances`: 1
- CPU: 1
- Memory: 512Mi
- Only Cloud Run + Cloud Build + Artifact Registry + required APIs

## Live endpoints

| Endpoint | Result |
|----------|--------|
| `GET /health` | HTTP 200 — artifacts missing (expected on fresh container) |
| `GET /metrics` | HTTP 200 — Prometheus text |
| `GET /v1/inventory/status` | HTTP 200 — `allow_mutations: false` |
| `GET /v1/data/summary` | HTTP 200 — empty local data |
| `POST /v1/ingest/inventree` | **HTTP 403** — mutation blocked |

### Smoke commands

```bash
export SERVICE_URL="https://invforge-ai-demo-289428962093.us-central1.run.app"

bash scripts/cloud_run_smoke.sh

# Or manually:
curl -fsS "$SERVICE_URL/health"
curl -fsS "$SERVICE_URL/metrics" | head -n 30
curl -fsS "$SERVICE_URL/v1/inventory/status"
curl -fsS "$SERVICE_URL/v1/data/summary"
curl -i -X POST "$SERVICE_URL/v1/ingest/inventree"   # expect 403
```

## Screenshots

| File | Source |
|------|--------|
| `cloud-run-health.png` | `$SERVICE_URL/health` JSON |
| `cloud-run-docs.png` | `$SERVICE_URL/docs` |
| `cloud-run-mutation-blocked.png` | POST ingest 403 curl output |

## What is live vs local-only

| Component | Live on Cloud Run? |
|-----------|------------------|
| AI Operations API (read-only) | **Yes** |
| Streamlit dashboard | No — local only |
| InvenTree core | No — not deployed |
| MLflow / ZenML / retraining | No — local only |
| kind Kubernetes profiles | No — local only |

## Cost warning

Charges may apply for Cloud Run request/CPU time, Cloud Build minutes, Artifact
Registry storage, and logs. Low-traffic demo with scale-to-zero can stay
low-cost, but **watch billing** in the GCP console.

## Teardown

```bash
gcloud run services delete invforge-ai-demo --region us-central1
```

Optionally delete the `cloud-run-source-deploy` Artifact Registry repository
if no longer needed. Do not delete billing-linked projects without review.

## Security confirmations

- No secrets committed
- No cloud credentials committed
- No InvenTree core deployed
- No dashboard deployed
- Not production
- No multi-cloud live claim
