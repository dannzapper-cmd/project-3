#!/usr/bin/env bash
# Tear down the InvForge Cloud Run dashboard service (PR-15 TEMPLATE).
set -euo pipefail

PROJECT_ID="${PROJECT_ID:?Set PROJECT_ID}"
REGION="${REGION:?Set REGION}"
SERVICE_NAME="${DASHBOARD_SERVICE_NAME:-invforge-dashboard-demo}"
IMAGE_URI="${DASHBOARD_IMAGE_URI:-}"

echo ">> Deleting Cloud Run service ${SERVICE_NAME}"
gcloud run services delete "${SERVICE_NAME}" \
  --region "${REGION}" \
  --project "${PROJECT_ID}" \
  --quiet

if [[ -n "${IMAGE_URI}" ]]; then
  echo ">> Optional: delete image ${IMAGE_URI} from Artifact Registry manually"
fi

echo ">> Dashboard teardown complete."
