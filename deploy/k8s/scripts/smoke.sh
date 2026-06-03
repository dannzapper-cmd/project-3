#!/usr/bin/env bash
# InvForge PR-11A — local Kubernetes smoke test.
#
# Verifies the AI Operations API is deployed and healthy via port-forward.
# Does NOT require BentoML or retraining (those are opt-in templates). Honest
# and self-contained: it only checks what PR-11A actually deploys.
#
# Usage: deploy/k8s/scripts/smoke.sh [namespace] [release]
set -euo pipefail

NS="${1:-invforge-ai}"
RELEASE="${2:-invforge}"
PORT="${INVFORGE_API_PORT:-8001}"
# Service name follows the chart's fullname convention. When the release name is
# "invforge" the fullname collapses to "invforge" (no doubled prefix).
if [ "$RELEASE" = "invforge" ]; then
  FULLNAME="invforge"
else
  FULLNAME="${RELEASE}-invforge"
fi
SVC="${FULLNAME}-ai-api"

echo "== InvForge k8s smoke (ns=${NS}, release=${RELEASE}) =="

echo "-- nodes --";       kubectl get nodes
echo "-- namespaces --";  kubectl get ns | grep -E 'invforge|NAME' || true
echo "-- pods --";        kubectl get pods -n "$NS"
echo "-- services --";    kubectl get svc -n "$NS"

echo "-- waiting for AI API rollout --"
kubectl rollout status deploy/"${SVC}" -n "$NS" --timeout=120s

echo "-- port-forward svc/${SVC} ${PORT}:${PORT} --"
kubectl port-forward -n "$NS" "svc/${SVC}" "${PORT}:${PORT}" >/tmp/invforge-pf.log 2>&1 &
PF_PID=$!
trap 'kill "$PF_PID" 2>/dev/null || true' EXIT

# Wait for the tunnel + a healthy /health.
ok=0
for _ in $(seq 1 30); do
  if curl -fsS "http://localhost:${PORT}/health" >/dev/null 2>&1; then ok=1; break; fi
  sleep 1
done
if [ "$ok" -ne 1 ]; then
  echo "FAIL: /health did not respond. port-forward log:"; cat /tmp/invforge-pf.log || true
  exit 1
fi

echo "-- GET /health --"
curl -fsS "http://localhost:${PORT}/health"; echo

# /metrics exists in the AI Ops image (observability group is installed).
echo "-- GET /metrics (first lines) --"
curl -fsS "http://localhost:${PORT}/metrics" | head -n 5 || echo "(metrics not available)"

echo "SMOKE OK."
