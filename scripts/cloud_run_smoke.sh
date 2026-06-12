#!/usr/bin/env bash
# Read-only smoke check for a live InvForge Cloud Run demo (PR-14).
# No credentials required. Mutation endpoint is verified blocked (403).
set -euo pipefail

BASE_URL="${SERVICE_URL:-${1:-}}"
if [[ -z "${BASE_URL}" ]]; then
  echo "Usage: SERVICE_URL=https://... $0" >&2
  echo "   or: $0 https://your-service.run.app" >&2
  exit 1
fi
BASE_URL="${BASE_URL%/}"

echo "InvForge Cloud Run smoke (read-only) against ${BASE_URL}"

curl -fsS "${BASE_URL}/health" | python3 -m json.tool >/dev/null
echo "  PASS: GET /health"

curl -fsS "${BASE_URL}/metrics" | head -n 5 >/dev/null
echo "  PASS: GET /metrics"

curl -fsS "${BASE_URL}/v1/inventory/status" | python3 -m json.tool >/dev/null
echo "  PASS: GET /v1/inventory/status"

curl -fsS "${BASE_URL}/v1/data/summary" | python3 -m json.tool >/dev/null
echo "  PASS: GET /v1/data/summary"

STATUS="$(curl -s -o /dev/null -w '%{http_code}' -X POST "${BASE_URL}/v1/ingest/inventree")"
if [[ "${STATUS}" != "403" ]]; then
  echo "  FAIL: POST /v1/ingest/inventree returned ${STATUS}, expected 403" >&2
  exit 1
fi
echo "  PASS: POST /v1/ingest/inventree blocked (403)"

echo "Smoke check PASSED (read-only, mutation blocked)."
