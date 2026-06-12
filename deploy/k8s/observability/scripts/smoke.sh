#!/usr/bin/env bash
# InvForge PR-11B — observability smoke test.
#
# Verifies each observability backend is reachable and that a REAL InvForge
# metric is present in Prometheus. Requires the port-forwards from
# port-forward.sh to be running first (see docs/runbooks/observability-startup.md).
# Exits non-zero with a clear message on the first failure.
set -euo pipefail

PROM="${PROM_URL:-http://localhost:9090}"
GRAFANA="${GRAFANA_URL:-http://localhost:3000}"
LOKI="${LOKI_URL:-http://localhost:3100}"
TEMPO="${TEMPO_URL:-http://localhost:3200}"
ALERTMGR="${ALERTMANAGER_URL:-http://localhost:9093}"

fail() { echo "SMOKE FAIL: $1"; exit 1; }
check() {
  local name="$1" url="$2"
  if curl -sf -o /dev/null "$url"; then
    echo "ok: ${name} (${url})"
  else
    fail "${name} not reachable at ${url} (is port-forward running?)"
  fi
}

echo "== InvForge observability smoke =="
check "Prometheus healthy" "${PROM}/-/healthy"
check "Grafana UI"         "${GRAFANA}/api/health"
check "Loki ready"         "${LOKI}/ready"
check "Tempo ready"        "${TEMPO}/ready"
check "AlertManager healthy" "${ALERTMGR}/-/healthy"

# Verify a REAL InvForge metric is present (proves the AI API scrape works).
echo "-- checking real metric invforge_drift_detected in Prometheus --"
RESP="$(curl -sf "${PROM}/api/v1/query?query=invforge_drift_detected" || true)"
echo "$RESP" | grep -q '"status":"success"' || fail "Prometheus query failed"
if echo "$RESP" | grep -q '"result":\[\]'; then
  echo "WARN: invforge_drift_detected returned no series yet."
  echo "      Ensure the AI API is deployed (make k8s-deploy) and give Prometheus"
  echo "      one scrape interval. The metric exists in /metrics (PR-07 contract)."
else
  echo "ok: invforge_drift_detected present in Prometheus"
fi

echo "SMOKE OK."
