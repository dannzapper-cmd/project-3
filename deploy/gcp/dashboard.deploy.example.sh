#!/usr/bin/env bash
# InvForge Dashboard — GCP Cloud Run deploy (PR-15 TEMPLATE).
#
# Deploys the read-only Streamlit dashboard as a SEPARATE Cloud Run service
# from the AI Operations API. Creates billable resources when run with creds.
set -euo pipefail

PROJECT_ID="${PROJECT_ID:?Set PROJECT_ID}"
REGION="${REGION:?Set REGION}"
SERVICE_NAME="${DASHBOARD_SERVICE_NAME:-invforge-dashboard-demo}"
IMAGE_URI="${DASHBOARD_IMAGE_URI:?Set DASHBOARD_IMAGE_URI}"
API_BASE_URL="${API_BASE_URL:?Set API_BASE_URL (live read-only API URL)}"
DEMO_PASSWORD="${INVFORGE_DEMO_PASSWORD:?Set INVFORGE_DEMO_PASSWORD (reviewer gate)}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

echo ">> Building dashboard image (Dockerfile.dashboard)"
if [[ "${SKIP_DASHBOARD_BUILD:-}" != "1" ]]; then
  docker build -f "${REPO_ROOT}/Dockerfile.dashboard" -t "${IMAGE_URI}" "${REPO_ROOT}"
  echo ">> Pushing image"
  docker push "${IMAGE_URI}"
else
  echo ">> SKIP_DASHBOARD_BUILD=1 — using existing image ${IMAGE_URI}"
fi

TMP_MANIFEST="$(mktemp)"
trap 'rm -f "${TMP_MANIFEST}"' EXIT
sed \
  -e "s|SERVICE_NAME|${SERVICE_NAME}|g" \
  -e "s|IMAGE_URI|${IMAGE_URI}|g" \
  -e "s|SA_EMAIL|${SA_EMAIL:-}|g" \
  -e "s|DEMO_PASSWORD_PLACEHOLDER|${DEMO_PASSWORD}|g" \
  -e "s|API_BASE_URL_PLACEHOLDER|${API_BASE_URL}|g" \
  "${REPO_ROOT}/deploy/gcp/dashboard.service.template.yaml" > "${TMP_MANIFEST}"

if [[ -z "${SA_EMAIL:-}" ]]; then
  sed -i.bak '/serviceAccountName:/d' "${TMP_MANIFEST}" && rm -f "${TMP_MANIFEST}.bak"
fi

echo ">> Deploying dashboard to Cloud Run"
gcloud run services replace "${TMP_MANIFEST}" \
  --region "${REGION}" \
  --project "${PROJECT_ID}"

echo ">> Allowing public access (reviewer gate protects dashboard content)"
gcloud run services add-iam-policy-binding "${SERVICE_NAME}" \
  --region "${REGION}" \
  --project "${PROJECT_ID}" \
  --member="allUsers" \
  --role="roles/run.invoker"

URL="$(gcloud run services describe "${SERVICE_NAME}" \
  --region "${REGION}" --project "${PROJECT_ID}" \
  --format='value(status.url)')"
echo ">> Dashboard URL: ${URL}"
echo ">> Demo login: user=${INVFORGE_DEMO_USER:-reviewer} password=<set via INVFORGE_DEMO_PASSWORD>"
echo ">> Teardown: DASHBOARD_SERVICE_NAME=${SERVICE_NAME} deploy/gcp/dashboard.teardown.example.sh"
