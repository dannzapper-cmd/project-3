# PR-13.1 — Live Cloud Run demo (read-only AI Operations API)

Date: 2026-06-12  
Repo: `/Users/danny/project-3-clean`  
Branch: `cursor/pr13-final-packaging`  
PR: https://github.com/dannzapper-cmd/project-3/pull/17  
Commit inspected: `61d506b37f6ca1acda08a3f7b1dbcf1d71984b08`

## Verdict

**BLOCKED — deployment not executed.**

`gcloud` CLI is not installed on this machine (`command -v gcloud` → not found).
No active GCP account or project could be verified. Per PR-13.1 stop conditions,
no Cloud Run service was created, no live URL exists, and README was **not**
updated to claim a live demo.

This is **not production**. This is **not** multi-cloud live deployment.

## Pre-deploy inspection (PASS)

Repo sanity:

| Check | Result |
|-------|--------|
| Path | `/Users/danny/project-3-clean` |
| Branch | `cursor/pr13-final-packaging` |
| HEAD | `61d506b37f6ca1acda08a3f7b1dbcf1d71984b08` |
| Remote | `origin` → `https://github.com/dannzapper-cmd/project-3.git` |

Deploy contract confirmed (`docs/deployment-contract.md`):

| Surface | Cloud Run demo? |
|---------|-----------------|
| `GET /health`, `/metrics`, `/v1/inventory/status`, `/v1/data/summary` | **Yes** (read-only) |
| `POST /v1/ingest/inventree` | **Blocked** (`INVFORGE_ALLOW_MUTATIONS=false` → HTTP 403) |
| InvenTree core | **Not deployed** |
| Streamlit dashboard | **Local-only** |
| MLflow / ZenML / retraining | **Local-only** |
| Real API tokens / secrets | **Not required** for read-only demo |

Dockerfile packages only `api/` + `observability/` with cloud-safe defaults
(`INVFORGE_ENV=cloud`, mutations blocked via config).

## gcloud environment (FAIL — stop condition)

```bash
command -v gcloud   # → not found
gcloud --version    # → not available
gcloud auth list    # → not available
gcloud config list  # → not available
ls ~/.config/gcloud # → directory not present
```

## Planned configuration (not applied)

| Setting | Value |
|---------|-------|
| Service name | `invforge-ai-demo` |
| Region | `us-central1` |
| `INVFORGE_ENV` | `cloud` |
| `INVFORGE_DEMO_MODE` | `true` |
| `INVFORGE_ALLOW_MUTATIONS` | `false` |
| `LOG_LEVEL` | `INFO` |
| min instances | `0` |
| max instances | `1` |
| memory | `512Mi` (retry `1Gi` only if build/runtime fails) |
| CPU | `1` |
| Public access | `--allow-unauthenticated` (read-only + mutation-blocked) |

## Deploy command (for Danny to run after installing gcloud)

From repo root, after auth and project setup:

```bash
gcloud auth login
gcloud config set project PROJECT_ID

# Enable APIs if not already enabled (billable project required):
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com

gcloud run deploy invforge-ai-demo \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars INVFORGE_ENV=cloud,INVFORGE_DEMO_MODE=true,INVFORGE_ALLOW_MUTATIONS=false,LOG_LEVEL=INFO \
  --max-instances 1 \
  --min-instances 0 \
  --memory 512Mi \
  --cpu 1
```

Alternative (repo template path): build/push image then
`./deploy/gcp/deploy.example.sh` with `SERVICE_NAME=invforge-ai-demo`.

## Smoke commands (run after successful deploy)

```bash
SERVICE_URL=$(gcloud run services describe invforge-ai-demo \
  --region us-central1 --format='value(status.url)')

curl -fsS "$SERVICE_URL/health" | tee /tmp/invforge-cloud-health.json
curl -fsS "$SERVICE_URL/metrics" | head -n 30
curl -fsS "$SERVICE_URL/v1/inventory/status" | tee /tmp/invforge-cloud-inventory-status.json
curl -fsS "$SERVICE_URL/v1/data/summary" | tee /tmp/invforge-cloud-data-summary.json

# Mutation blocking proof:
curl -i -X POST "$SERVICE_URL/v1/ingest/inventree"
# Expected: HTTP 403

python scripts/deploy_smoke.py --base-url "$SERVICE_URL"
```

## Screenshots (NOT captured)

Blocked — no `SERVICE_URL`. Do not fake screenshots.

After deploy, capture:

- `docs/assets/screenshots/cloud-run-health.png` ← `$SERVICE_URL/health`
- `docs/assets/screenshots/cloud-run-docs.png` ← `$SERVICE_URL/docs`
- Optional: `cloud-run-mutation-blocked.png` ← 403 from POST ingest

## Teardown (document only — service not created)

When the demo is no longer needed:

```bash
gcloud run services delete invforge-ai-demo --region us-central1
```

Also watch GCP billing, delete Artifact Registry images if created by
`--source` deploy, and keep `max-instances 1` / `min-instances 0` to limit cost.

## Install gcloud (macOS)

```bash
# Homebrew (recommended)
brew install --cask google-cloud-sdk

# Or official installer
curl -O https://dl.google.com/dl/cloudsdk/channels/rapid/downloads/google-cloud-cli-darwin-arm.tar.gz
tar -xf google-cloud-cli-darwin-arm.tar.gz
./google-cloud-sdk/install.sh
```

Then:

```bash
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
```

## Security confirmations (this PR-13.1 pass)

- No secrets committed
- No cloud credentials committed or used
- No InvenTree core deployed
- No dashboard deployed
- No production claim
- No multi-cloud live claim
- No live Cloud Run service created

## Next action for Danny

1. Install and authenticate `gcloud` with a billing-enabled GCP project.
2. Run the deploy command above.
3. Run smoke tests and capture screenshots.
4. Update `README.md` with a **Live Cloud Run demo** section (only after proof).
5. Re-run `uv run ruff check .`, `uv run pytest`, `make secrets-scan`, `make security-check`.
6. Push evidence to PR #17.
