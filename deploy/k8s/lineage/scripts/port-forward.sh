#!/usr/bin/env bash
# InvForge PR-11B — port-forward Marquez (UI + API) from kind to localhost.
set -euo pipefail
NS="${1:-invforge-lineage}"
PIDFILE="/tmp/invforge-lineage-pf.pids"
: > "$PIDFILE"

fwd() {
  local svc="$1" port="$2"
  kubectl -n "$NS" port-forward "svc/${svc}" "${port}:${port}" >"/tmp/invforge-pf-${svc}.log" 2>&1 &
  echo $! >> "$PIDFILE"
  echo "port-forward ${svc} -> localhost:${port} (pid $!)"
}

echo "== Port-forwarding Marquez (ns=${NS}) =="
fwd marquez-web 3000
fwd marquez-api 5000
sleep 3
echo "Marquez UI: http://localhost:3000   API: http://localhost:5000"
echo "Stop with: while read p; do kill \$p; done < ${PIDFILE}"
