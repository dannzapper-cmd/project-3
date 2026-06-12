#!/usr/bin/env bash
# Stop the port-forwards started by port-forward.sh.
set -euo pipefail
PIDFILE="/tmp/invforge-obs-pf.pids"
if [ -f "$PIDFILE" ]; then
  while read -r pid; do
    [ -n "$pid" ] && kill "$pid" 2>/dev/null && echo "killed $pid" || true
  done < "$PIDFILE"
  rm -f "$PIDFILE"
else
  echo "No PID file found ($PIDFILE); nothing to stop."
fi
