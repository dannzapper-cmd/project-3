#!/usr/bin/env bash
# InvForge AI Operations Layer — GCP Cloud Run teardown (PR-10 TEMPLATE).
#
# Deletes the Cloud Run service and (optionally) the Artifact Registry image to
# stop ongoing charges. Set PROJECT_ID, REGION, SERVICE_NAME before running.
# This is NOT run by CI.
set -euo pipefail

PROJECT_ID="${PROJECT_ID:?Set PROJECT_ID}"
REGION="${REGION:?Set REGION}"
SERVICE_NAME="${SERVICE_NAME:?Set SERVICE_NAME}"

echo ">> Deleting Cloud Run service: ${SERVICE_NAME}"
gcloud run services delete "${SERVICE_NAME}" \
  --region "${REGION}" \
  --project "${PROJECT_ID}" \
  --quiet

# Optional: delete the pushed image to avoid Artifact Registry storage charges.
# Set IMAGE_URI to remove it.
if [[ -n "${IMAGE_URI:-}" ]]; then
  echo ">> Deleting image: ${IMAGE_URI}"
  gcloud artifacts docker images delete "${IMAGE_URI}" \
    --project "${PROJECT_ID}" \
    --quiet || echo "   (image delete skipped/failed; remove manually if needed)"
fi

echo ">> Teardown complete. Verify no Cloud Run services remain:"
echo "   gcloud run services list --region ${REGION} --project ${PROJECT_ID}"
echo ">> Also review Artifact Registry repositories and Secret Manager secrets."
