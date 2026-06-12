# GCP — Cloud Run deploy profile (primary, PR-10)

> **Status:** Deployment profile available. **Not actively deployed.** This
> profile configures a Cloud Run deployment of the InvForge AI Operations Layer.
> Activate it manually with your own credentials by following this README. It
> has not been deployed or smoke-tested in CI.

Google **Cloud Run** is the **primary** deploy target for InvForge. It is a
fully managed, scale-to-zero container runtime — a good fit for a low-cost,
read-only AI Operations demo surface (the external sidecar over InvenTree).

## What gets deployed

Only the **AI Operations API** container (see the repo-root `Dockerfile`):

- `GET /health` — health/status (SAFE, read-only)
- `GET /metrics` — Prometheus metrics (SAFE, read-only)
- `GET /v1/inventory/status` — read-only config/status (SAFE)
- `GET /v1/data/summary` — read-only local data summary (SAFE)
- `POST /v1/ingest/inventree` — **UNSAFE / blocked** in cloud mode
  (`INVFORGE_ALLOW_MUTATIONS=false`)

InvenTree core, MLflow, ZenML, retraining, and the Streamlit dashboard API
container are **not** in the API image. The **dashboard** has a separate
Cloud Run profile (`Dockerfile.dashboard`, `deploy/gcp/dashboard.*`). See
`docs/cloud/gcp-cloud-run-activation.md`.

## Files

| File | Purpose |
|------|---------|
| `service.template.yaml` | Cloud Run API service manifest |
| `dashboard.service.template.yaml` | Cloud Run dashboard service manifest (PR-15) |
| `env.example` | Deploy variables template (copy to a git-ignored `.env`) |
| `deploy.example.sh` | Build → push → deploy → verify API |
| `dashboard.deploy.example.sh` | Build → push → deploy → verify dashboard |
| `teardown.example.sh` | Delete the API service |
| `dashboard.teardown.example.sh` | Delete the dashboard service |
| `cloud-armor.template.yaml` | WAF/DDoS profile template (activation-ready, not live) |

## Prerequisites

- A GCP project with billing enabled.
- `gcloud` CLI authenticated (`gcloud auth login`).
- Enabled APIs: Cloud Run, Artifact Registry (and Secret Manager if using secrets).
- Docker available locally to build/push the image.

## Image build & push

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

## Deploy / update

```bash
# Reads PROJECT_ID, REGION, SERVICE_NAME, IMAGE_URI (and optional SA_EMAIL)
./deploy/gcp/deploy.example.sh
```

This renders `service.template.yaml`, runs `gcloud run services replace`,
optionally grants public read-only access, and prints the service URL.

## Required env vars (injected into the container)

| Var | Type | Notes |
|-----|------|-------|
| `PORT` | plain | Injected by Cloud Run; container binds `uvicorn` to it |
| `INVFORGE_ENV` | plain | `cloud` (read-only, mutations blocked) |
| `INVFORGE_DEMO_MODE` | plain | `true` so `/health` stays 200 without local artifacts |
| `INVFORGE_ALLOW_MUTATIONS` | plain | **`false`** — never `true` on a public service |
| `LOG_LEVEL` | plain | e.g. `INFO` |

## Optional / secret env vars

Anything sensitive (e.g. a real `INVENTREE_API_TOKEN`) must come from
**Secret Manager**, never inlined:

```bash
echo -n "REPLACE_WITH_TOKEN" | gcloud secrets create invforge-inventree-api-token \
  --data-file=- --project "${PROJECT_ID}"
```

Then reference it via `secretKeyRef` in `service.template.yaml` (a commented
example is included). Secrets are only needed if you intentionally enable live
ingestion — the default demo surface is read-only and needs none.

## Health check / smoke verification

The template wires startup + liveness probes to `/health`. After deploy:

```bash
URL=$(gcloud run services describe "${SERVICE_NAME}" \
  --region "${REGION}" --project "${PROJECT_ID}" --format='value(status.url)')
python scripts/deploy_smoke.py --base-url "${URL}"
```

## Public vs private access

`deploy.example.sh` grants `allUsers` the `run.invoker` role for a public,
read-only demo. Because all mutation endpoints are blocked in cloud mode, the
public surface is read-only. To keep it private, comment out the
`add-iam-policy-binding` step and invoke with an identity token.

## WAF / DDoS (Cloud Armor)

`cloud-armor.template.yaml` is an **activation-ready template**. WAF/DDoS
protection is **not active** out of the box: Cloud Run must be fronted by an
external HTTPS load balancer + serverless NEG for Cloud Armor to apply. See the
template header for the architecture and `gcloud` equivalents. Activation
requires a GCP account, a load balancer, and (for some tiers) verifying current
Cloud Armor pricing/eligibility.

## Cost guardrails

- `minScale: 0` → scale to zero when idle (no always-on compute charges); cold
  starts are the trade-off.
- `maxScale: 3` caps concurrent instances to prevent runaway cost.
- **What can cause charges:** request/CPU/memory time while serving, Artifact
  Registry image storage, egress, audit/log retention, and (if enabled) Cloud
  Armor / load balancer.
- Low-traffic demo can often stay near free-tier levels, depending on account
  eligibility, region, request volume, image storage, logs, and current
  provider pricing. **Verify current pricing/free-tier limits in the official
  GCP docs before deploying.** Actual costs may change.

## Teardown

```bash
export IMAGE_URI="..."   # optional, to also delete the image
./deploy/gcp/teardown.example.sh
```

Also review Artifact Registry repositories, Secret Manager secrets, and any
load balancer / Cloud Armor resources you created. See
`docs/costs/deployment-costs.md`.

## Known limitations

- Not deployed or smoke-tested in CI; no live GCP resources are maintained.
- Scale-to-zero means first-request cold starts.
- Cloud Armor requires extra load-balancer architecture (template only).
- Kubernetes/GKE is **deferred to PR-11 Senior Edition**.
