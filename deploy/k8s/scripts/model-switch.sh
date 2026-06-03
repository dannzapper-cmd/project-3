#!/usr/bin/env bash
# InvForge PR-11A — blue-green model switch for the BentoML Service.
#
# Patches the BentoML Service selector to point at the requested color. This is
# the blue-green switch: one Service, one active color at a time.
#
# PREREQUISITE: a real BentoML image must be built, loaded, and deployed
# (bentoml.enabled=true with the target color deployment enabled). Until then
# this is a documented, ready-to-use control plane, NOT an operable switch
# (see docs/runbooks/model-rollback.md and docs/adr/002-pr11a-kubernetes-scope.md).
#
# Usage: deploy/k8s/scripts/model-switch.sh <blue|green> [namespace] [release]
set -euo pipefail

COLOR="${1:?usage: model-switch.sh <blue|green> [namespace] [release]}"
NS="${2:-invforge-ai}"
RELEASE="${3:-invforge}"
if [ "$RELEASE" = "invforge" ]; then
  FULLNAME="invforge"
else
  FULLNAME="${RELEASE}-invforge"
fi
SVC="${FULLNAME}-bentoml"

case "$COLOR" in
  blue|green) ;;
  *) echo "ERROR: color must be 'blue' or 'green' (got '$COLOR')"; exit 1 ;;
esac

if ! kubectl get svc "$SVC" -n "$NS" >/dev/null 2>&1; then
  echo "ERROR: Service '$SVC' not found in namespace '$NS'."
  echo "       BentoML is disabled in PR-11A. Build/deploy a real image first:"
  echo "       make bento-build && make bento-containerize && make k8s-load-bento"
  exit 1
fi

echo "Switching BentoML active color -> ${COLOR} (svc/${SVC}, ns ${NS})"
kubectl patch svc "$SVC" -n "$NS" --type merge \
  -p "{\"spec\":{\"selector\":{\"invforge.io/model-color\":\"${COLOR}\"}}}"
echo "Done. Verify:"
echo "  kubectl get endpoints ${SVC} -n ${NS}"
