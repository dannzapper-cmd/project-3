#!/usr/bin/env bash
# InvForge AI Operations Layer — GCP Cloud Run deploy (PR-10 TEMPLATE).
#
# This is a TEMPLATE. Set PROJECT_ID, REGION, SERVICE_NAME, and IMAGE_URI
# before running (export them or source deploy/gcp/.env). It is NOT run by CI
# and creates real, billable cloud resources when executed with credentials.
#
# Prereqs: gcloud CLI authenticated (`gcloud auth login`), billing enabled,
# Cloud Run + Artifact Registry APIs enabled, and Docker available to build.
set -euo pipefail

PROJECT_ID="${PROJECT_ID:?Set PROJECT_ID (e.g. export PROJECT_ID=my-project)}"
REGION="${REGION:?Set REGION (e.g. export REGION=us-central1)}"
SERVICE_NAME="${SERVICE_NAME:?Set SERVICE_NAME (e.g. export SERVICE_NAME=invforge-ai-ops)}"
IMAGE_URI="${IMAGE_URI:?Set IMAGE_URI (Artifact Registry image, e.g. REGION-docker.pkg.dev/PROJECT_ID/invforge/ai-ops:latest)}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

echo ">> Building the AI Operations image (runtime-only; see Dockerfile)"
docker build -t "${IMAGE_URI}" "${REPO_ROOT}"

echo ">> Pushing image to Artifact Registry"
# Requires: gcloud auth configure-docker REGION-docker.pkg.dev
docker push "${IMAGE_URI}"

echo ">> Rendering Cloud Run service from template"
TMP_MANIFEST="$(mktemp)"
trap 'rm -f "${TMP_MANIFEST}"' EXIT
sed \
  -e "s|SERVICE_NAME|${SERVICE_NAME}|g" \
  -e "s|IMAGE_URI|${IMAGE_URI}|g" \
  -e "s|SA_EMAIL|${SA_EMAIL:-}|g" \
  "${REPO_ROOT}/deploy/gcp/service.template.yaml" > "${TMP_MANIFEST}"

# Drop the serviceAccountName line if SA_EMAIL was not provided.
if [[ -z "${SA_EMAIL:-}" ]]; then
  sed -i.bak '/serviceAccountName:/d' "${TMP_MANIFEST}" && rm -f "${TMP_MANIFEST}.bak"
fi

echo ">> Deploying to Cloud Run"
gcloud run services replace "${TMP_MANIFEST}" \
  --region "${REGION}" \
  --project "${PROJECT_ID}"

# Public, unauthenticated access for a read-only demo surface. Comment this out
# to keep the service private (then access requires IAM-authenticated invokers).
echo ">> Allowing public (unauthenticated) access — read-only demo only"
gcloud run services add-iam-policy-binding "${SERVICE_NAME}" \
  --region "${REGION}" \
  --project "${PROJECT_ID}" \
  --member="allUsers" \
  --role="roles/run.invoker"

echo ">> Verifying deployment"
URL="$(gcloud run services describe "${SERVICE_NAME}" \
  --region "${REGION}" --project "${PROJECT_ID}" \
  --format='value(status.url)')"

echo ">> Service URL: ${URL}"
echo ">> Run a read-only smoke check:"
echo "   python scripts/deploy_smoke.py --base-url ${URL}"
echo ">> Remember to tear down when done: deploy/gcp/teardown.example.sh"
