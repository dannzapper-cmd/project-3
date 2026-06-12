#!/usr/bin/env bash
# InvForge PR-11B — lineage smoke. Requires Marquez port-forwarded on :5000.
#
# Emits ONE real OpenLineage run via the verified retraining pipeline
# (make retrain-smoke with OPENLINEAGE_URL set) and confirms Marquez recorded the
# 'invforge.retraining' job. Honest end-to-end check of the lineage loop.
set -euo pipefail

MARQUEZ="${OPENLINEAGE_URL:-http://localhost:5000}"

echo "== InvForge lineage smoke =="
echo "-- checking Marquez API at ${MARQUEZ} --"
curl -sf "${MARQUEZ}/api/v1/namespaces" >/dev/null \
  || { echo "FAIL: Marquez API not reachable at ${MARQUEZ} (port-forward marquez-api 5000?)"; exit 1; }

echo "-- emitting a real retraining run with OpenLineage enabled --"
OPENLINEAGE_URL="${MARQUEZ}" make retrain-smoke

echo "-- querying Marquez for the invforge.retraining job --"
RESP="$(curl -sf "${MARQUEZ}/api/v1/namespaces/invforge/jobs" || true)"
if echo "$RESP" | grep -q "invforge.retraining"; then
  echo "PASS: Marquez shows job 'invforge.retraining'."
else
  echo "FAIL: job not found in Marquez yet. Response was:"
  echo "$RESP" | head -c 500
  exit 1
fi
