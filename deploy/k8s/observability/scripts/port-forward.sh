#!/usr/bin/env bash
# InvForge PR-11B — port-forward the observability stack from kind to localhost.
# Backgrounds one port-forward per service and writes PIDs to /tmp so
# obs-stop-forward.sh can clean them up. Re-run obs-k8s-smoke after this.
set -euo pipefail

NS="${1:-invforge-observability}"
PIDFILE="/tmp/invforge-obs-pf.pids"
: > "$PIDFILE"

fwd() {
  local svc="$1" port="$2"
  kubectl -n "$NS" port-forward "svc/${svc}" "${port}:${port}" >"/tmp/invforge-pf-${svc}.log" 2>&1 &
  echo $! >> "$PIDFILE"
  echo "port-forward ${svc} -> localhost:${port} (pid $!)"
}

echo "== Port-forwarding observability services (ns=${NS}) =="
fwd grafana 3000
fwd prometheus 9090
fwd loki 3100
fwd tempo 3200
fwd alertmanager 9093

echo "Waiting for tunnels..."; sleep 4
echo "Done. Stop them with: bash deploy/k8s/observability/scripts/stop-forward.sh"
