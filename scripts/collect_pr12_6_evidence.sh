#!/usr/bin/env bash
# InvForge PR-12.6 — local senior QA evidence collector.
# Default: static checks only. Heavy stacks (Docker/kind/obs/lineage) are opt-in.
# Does not run cloud mutation commands or require credentials.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
EVIDENCE_ROOT="${EVIDENCE_ROOT:-docs/evidence/pr12-6-local/${TIMESTAMP}}"
LOG_DIR="${EVIDENCE_ROOT}/logs"
SUMMARY="${EVIDENCE_ROOT}/SUMMARY.md"

RUN_STATIC=0
RUN_DOCKER=0
RUN_K8S=0
RUN_OBS=0
RUN_OBS_COMBINED=0
RUN_LINEAGE=0
SKIP_HEAVY=0

usage() {
  cat <<'EOF'
Usage: bash scripts/collect_pr12_6_evidence.sh [OPTIONS]

Collect PR-12.6 senior QA evidence into docs/evidence/pr12-6-local/<timestamp>/.

Options (at least one required; default is --static when no flags given):
  --static       Offline/static checks (uv, ruff, pytest, make targets)
  --docker       Docker build + smoke (teardown after)
  --k8s          kind AI layer (teardown after)
  --observability  PR-11B observability profile (requires kind; teardown after)
  --observability-combined  AI layer + observability + alert-test (sequential teardown)
  --lineage      PR-11B lineage profile (requires kind; teardown after)
  --all-local    Run static then each heavy section sequentially (one stack at a time)
  --skip-heavy   With --all-local, run static only (alias for static-only all-local)

Heavy sections are opt-in. Run one at a time on 8 GB machines.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --static) RUN_STATIC=1 ;;
    --docker) RUN_DOCKER=1 ;;
    --k8s) RUN_K8S=1 ;;
    --observability) RUN_OBS=1 ;;
    --observability-combined) RUN_OBS_COMBINED=1 ;;
    --lineage) RUN_LINEAGE=1 ;;
    --all-local) RUN_STATIC=1; RUN_DOCKER=1; RUN_K8S=1; RUN_OBS=1; RUN_LINEAGE=1 ;;
    --skip-heavy) SKIP_HEAVY=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 2 ;;
  esac
  shift
done

if [[ "$RUN_STATIC$RUN_DOCKER$RUN_K8S$RUN_OBS$RUN_OBS_COMBINED$RUN_LINEAGE" == "000000" ]]; then
  RUN_STATIC=1
fi

if [[ "$SKIP_HEAVY" -eq 1 ]]; then
  RUN_DOCKER=0
  RUN_K8S=0
  RUN_OBS=0
  RUN_OBS_COMBINED=0
  RUN_LINEAGE=0
fi

mkdir -p "$LOG_DIR"
RESULTS_FILE="${LOG_DIR}/results.tsv"
: > "$RESULTS_FILE"

log() { echo "[$(date +%H:%M:%S)] $*" | tee -a "${LOG_DIR}/collector.log"; }

record_result() {
  printf '%s\t%s\n' "$1" "$2" >> "$RESULTS_FILE"
}

get_result() {
  awk -F '\t' -v k="$1" '$1 == k { print $2; exit }' "$RESULTS_FILE"
}

redact_env() {
  env | sort | sed -E \
    -e 's/((TOKEN|SECRET|PASSWORD|KEY|CREDENTIAL|API_KEY)=).*/\1[REDACTED]/Ig' \
    -e 's/(AWS_|GCP_|AZURE_|GOOGLE_).*/\1[REDACTED]/'
}

write_tools() {
  {
    echo "# Tool availability — ${TIMESTAMP}"
    echo
    for cmd in uv docker kind kubectl helm kubeconform trivy syft make curl; do
      if command -v "$cmd" >/dev/null 2>&1; then
        echo "- ${cmd}: $(command -v "$cmd")"
        case "$cmd" in
          uv) uv --version 2>&1 || true ;;
          docker) docker --version 2>&1 || true ;;
          kind) kind --version 2>&1 || true ;;
          kubectl) kubectl version --client 2>&1 || true ;;
          helm) helm version --short 2>&1 || true ;;
          kubeconform) kubeconform -v 2>&1 || true ;;
          trivy) trivy --version 2>&1 || true ;;
          syft) syft version 2>&1 || true ;;
        esac
      else
        echo "- ${cmd}: NOT FOUND"
      fi
    done
    echo
    echo "## Docker daemon"
    if docker info >/dev/null 2>&1; then
      echo "AVAILABLE"
    else
      echo "NOT AVAILABLE"
    fi
    echo
    echo "## Git"
    git -C "$REPO_ROOT" branch --show-current
    git -C "$REPO_ROOT" rev-parse HEAD
    echo
    echo "## Environment (redacted)"
    redact_env
  } > "${EVIDENCE_ROOT}/tools.txt"
}

require_make_target() {
  local target="$1"
  if ! make -n "$target" >/dev/null 2>&1; then
    log "ERROR: Makefile target '${target}' missing — repo mismatch?"
    record_result "make:${target}" "FAIL"
    return 1
  fi
}

run_step() {
  local key="$1"
  shift
  local logfile="${LOG_DIR}/${key}.log"
  log "RUN: $*"
  set +e
  (
    set -o pipefail
    "$@" 2>&1 | tee "$logfile"
  )
  local rc=${PIPESTATUS[0]}
  set -e
  if [[ $rc -eq 0 ]]; then
    record_result "$key" "PASS"
    log "PASS: $key"
  else
    record_result "$key" "FAIL"
    log "FAIL: $key (exit $rc)"
  fi
  return 0
}

docker_available() {
  command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1
}

kind_cluster_exists() {
  kind get clusters 2>/dev/null | grep -qx invforge-local
}

ensure_kind_cluster() {
  if kind_cluster_exists; then
    log "kind cluster invforge-local already exists"
    return 0
  fi
  require_make_target docker-build-ai
  require_make_target k8s-up
  run_step k8s-preflight make k8s-preflight
  [[ "$(get_result k8s-preflight)" == PASS ]] || return 1
  run_step docker-build-ai make docker-build-ai
  [[ "$(get_result docker-build-ai)" == PASS ]] || return 1
  run_step k8s-up make k8s-up
  [[ "$(get_result k8s-up)" == PASS ]]
}

kill_pf() {
  local pidfile="$1"
  [[ -f "$pidfile" ]] || return 0
  while read -r p; do
    kill "$p" 2>/dev/null || true
  done < "$pidfile"
  rm -f "$pidfile"
}

section_static() {
  log "=== STATIC CHECKS ==="
  local targets=(
    "uv-lock-check:uv lock --check"
    "ruff:uv run ruff check ."
    "pytest:uv run pytest"
    "deploy-validate:make deploy-validate"
    "secrets-scan:make secrets-scan"
    "security-check:make security-check"
    "retrain-smoke:make retrain-smoke"
    "retraining-check:make retraining-check"
    "helm-lint:make helm-lint"
    "helm-template:make helm-template"
    "obs-k8s-lint:make obs-k8s-lint"
    "obs-k8s-template:make obs-k8s-template"
    "lineage-lint:make lineage-lint"
  )
  if command -v trivy >/dev/null 2>&1; then
    targets+=("trivy-scan:make trivy-scan")
  else
    record_result "trivy-scan" "NOT RUN"
    log "trivy not installed; skipping trivy-scan"
  fi
  if command -v syft >/dev/null 2>&1; then
    targets+=("sbom:make sbom")
  else
    record_result "sbom" "NOT RUN"
    log "syft not installed; skipping sbom"
  fi
  for entry in "${targets[@]}"; do
    local key="${entry%%:*}"
    local cmd="${entry#*:}"
    if [[ "$cmd" == make* ]]; then
      local target="${cmd#make }"
      require_make_target "$target" || continue
    fi
    run_step "$key" bash -c "$cmd"
  done
}

section_docker() {
  log "=== DOCKER ==="
  if ! docker_available; then
    record_result "docker" "NOT RUN"
    log "Docker daemon unavailable — skipping Docker section"
    return 0
  fi
  for t in docker-config docker-build-ai docker-smoke; do
    require_make_target "$t" || return 1
  done
  run_step docker-config make docker-config
  run_step docker-build-ai make docker-build-ai
  run_step docker-smoke make docker-smoke
  run_step docker-down make docker-down || true
}

section_k8s() {
  log "=== K8S AI LAYER ==="
  if ! docker_available; then
    record_result "k8s" "NOT RUN"
    log "Docker daemon unavailable — skipping k8s section"
    return 0
  fi
  for t in k8s-preflight k8s-up k8s-deploy k8s-status k8s-smoke k8s-down; do
    require_make_target "$t" || return 1
  done
  run_step k8s-preflight make k8s-preflight
  run_step docker-build-ai make docker-build-ai
  run_step k8s-up make k8s-up
  run_step k8s-deploy make k8s-deploy
  run_step k8s-status make k8s-status
  run_step k8s-smoke make k8s-smoke
  run_step kubectl-pods kubectl get pods -A
  run_step k8s-down make k8s-down
}

section_observability() {
  log "=== OBSERVABILITY ==="
  if ! docker_available; then
    record_result "observability" "NOT RUN"
    return 0
  fi
  if ! command -v kubectl >/dev/null 2>&1; then
    record_result "observability" "NOT RUN"
    log "kubectl missing — skipping observability"
    return 0
  fi
  for t in obs-k8s-up obs-k8s-status obs-k8s-smoke obs-k8s-down; do
    require_make_target "$t" || return 1
  done
  ensure_kind_cluster || { record_result "observability" "FAIL"; return 0; }
  run_step obs-k8s-up make obs-k8s-up
  run_step obs-wait kubectl wait --for=condition=available deployment --all \
    -n invforge-observability --timeout=300s
  run_step obs-k8s-status make obs-k8s-status
  run_step obs-port-forward bash deploy/k8s/observability/scripts/port-forward.sh invforge-observability
  sleep 5
  run_step obs-k8s-smoke make obs-k8s-smoke
  if kubectl get ns invforge-ai >/dev/null 2>&1 && require_make_target obs-k8s-alert-test; then
    run_step obs-k8s-alert-test make obs-k8s-alert-test || true
  else
    record_result "obs-k8s-alert-test" "NOT RUN"
    log "Skipping obs-k8s-alert-test (invforge-ai namespace not deployed)"
  fi
  bash deploy/k8s/observability/scripts/stop-forward.sh >/dev/null 2>&1 || kill_pf /tmp/invforge-obs-pf.pids
  run_step obs-k8s-down make obs-k8s-down
}

section_observability_combined() {
  log "=== OBSERVABILITY COMBINED (AI + obs + alert-test) ==="
  if ! docker_available; then
    record_result "observability-combined" "NOT RUN"
    return 0
  fi
  if ! command -v kubectl >/dev/null 2>&1; then
    record_result "observability-combined" "NOT RUN"
    return 0
  fi
  for t in k8s-preflight k8s-up k8s-deploy k8s-smoke obs-k8s-up obs-k8s-smoke obs-k8s-alert-test obs-k8s-down k8s-down; do
    require_make_target "$t" || return 1
  done
  run_step k8s-preflight make k8s-preflight
  run_step docker-build-ai make docker-build-ai
  run_step k8s-up make k8s-up
  run_step k8s-deploy make k8s-deploy
  run_step k8s-wait kubectl wait --for=condition=available deployment --all \
    -n invforge-ai --timeout=300s
  run_step k8s-smoke make k8s-smoke
  run_step obs-k8s-up make obs-k8s-up
  run_step obs-wait kubectl wait --for=condition=available deployment --all \
    -n invforge-observability --timeout=300s
  run_step obs-port-forward bash deploy/k8s/observability/scripts/port-forward.sh invforge-observability
  sleep 8
  run_step obs-k8s-smoke make obs-k8s-smoke
  run_step obs-k8s-alert-test make obs-k8s-alert-test
  run_step kubectl-all kubectl get pods -A
  bash deploy/k8s/observability/scripts/stop-forward.sh >/dev/null 2>&1 || kill_pf /tmp/invforge-obs-pf.pids
  run_step obs-k8s-down make obs-k8s-down
  run_step k8s-down make k8s-down
}

section_lineage() {
  log "=== LINEAGE ==="
  if ! docker_available; then
    record_result "lineage" "NOT RUN"
    return 0
  fi
  if ! command -v kubectl >/dev/null 2>&1; then
    record_result "lineage" "NOT RUN"
    return 0
  fi
  for t in lineage-up lineage-status lineage-smoke lineage-down; do
    require_make_target "$t" || return 1
  done
  ensure_kind_cluster || { record_result "lineage" "FAIL"; return 0; }
  run_step lineage-up make lineage-up
  run_step lineage-wait kubectl wait --for=condition=available deployment --all \
    -n invforge-lineage --timeout=300s
  run_step lineage-status make lineage-status
  bash deploy/k8s/lineage/scripts/port-forward.sh invforge-lineage \
    > "${LOG_DIR}/lineage-port-forward.log" 2>&1
  run_step lineage-smoke make lineage-smoke
  kill_pf /tmp/invforge-lineage-pf.pids
  run_step lineage-down make lineage-down
}

write_summary() {
  {
    echo "# PR-12.6 Local Evidence Summary"
    echo
    echo "- Timestamp: ${TIMESTAMP}"
    echo "- Repo: ${REPO_ROOT}"
    echo "- Branch: $(git branch --show-current)"
    echo "- HEAD: $(git rev-parse HEAD)"
    echo
    echo "## Results"
    echo
    echo "| Check | Status |"
    echo "|-------|--------|"
    sort "$RESULTS_FILE" | while IFS=$'\t' read -r key status; do
      echo "| ${key} | ${status} |"
    done
    echo
    echo "## Logs"
    echo
    echo "See \`${LOG_DIR}/\` for per-step logs."
    echo
    echo "## Notes"
    echo
    echo "- Heavy stacks run sequentially; do not run Docker + kind + obs + lineage together on 8 GB RAM."
    echo "- No cloud resources were created by this script."
    echo "- GitHub Actions CI must still be verified manually in the GitHub UI."
  } > "$SUMMARY"
  log "Wrote ${SUMMARY}"
}

main() {
  log "Evidence root: ${EVIDENCE_ROOT}"
  write_tools
  [[ "$RUN_STATIC" -eq 1 ]] && section_static
  [[ "$RUN_DOCKER" -eq 1 ]] && section_docker
  [[ "$RUN_K8S" -eq 1 ]] && section_k8s
  [[ "$RUN_OBS" -eq 1 ]] && section_observability
  [[ "$RUN_OBS_COMBINED" -eq 1 ]] && section_observability_combined
  [[ "$RUN_LINEAGE" -eq 1 ]] && section_lineage
  write_summary
  echo ""
  echo "Evidence collected under: ${EVIDENCE_ROOT}"
}

main
