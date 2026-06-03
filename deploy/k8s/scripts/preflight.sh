#!/usr/bin/env bash
# InvForge PR-11A — preflight checks for the local Kubernetes workflow.
# Verifies required tools exist (with install hints) and warns if InvenTree's
# Docker Compose stack is running (to avoid OOM on an 8 GB laptop).
set -euo pipefail

MIN_KIND="0.23"
MIN_KUBECTL="1.29"
MIN_HELM="3.14"

fail=0

need() {
  local bin="$1" hint="$2"
  if ! command -v "$bin" >/dev/null 2>&1; then
    echo "ERROR: '$bin' not found. Install it: $hint"
    fail=1
  else
    echo "ok: $bin -> $(command -v "$bin")"
  fi
}

echo "== InvForge k8s preflight =="
need kind    "https://kind.sigs.k8s.io/docs/user/quick-start/#installation (>= ${MIN_KIND})"
need kubectl "https://kubernetes.io/docs/tasks/tools/ (>= ${MIN_KUBECTL})"
need helm    "https://helm.sh/docs/intro/install/ (>= ${MIN_HELM})"
need docker  "https://docs.docker.com/get-docker/ (kind needs a container runtime)"

# Warn if InvenTree Compose is running — running both can OOM an 8 GB laptop.
if command -v docker >/dev/null 2>&1; then
  if docker compose -f app/docker-compose.yml ps --quiet 2>/dev/null | grep -q .; then
    echo "WARNING: InvenTree Docker Compose appears to be running."
    echo "         Stop it first to avoid OOM on 8 GB RAM:  make docker-down"
  fi
fi

if [ "$fail" -ne 0 ]; then
  echo "Preflight FAILED: install the missing tools above and retry."
  exit 1
fi
echo "Preflight OK."
