#!/usr/bin/env bash
# InvForge PR-11B — end-to-end alert loop test.
#
# Triggers a REAL alert condition (InvForgeAIDown) by scaling the AI API to 0,
# then confirms the webhook receiver logged the alert. Restores the AI API after.
# Closes the loop: metric (up==0) -> rule -> AlertManager -> webhook -> log.
set -euo pipefail

AI_NS="${AI_NS:-invforge-ai}"
OBS_NS="${OBS_NS:-invforge-observability}"
AI_DEPLOY="${AI_DEPLOY:-invforge-ai-api}"
WAIT="${WAIT:-180}"

echo "== Alert loop test: InvForgeAIDown =="
echo "-- scaling ${AI_DEPLOY} to 0 in ${AI_NS} (simulates API down) --"
kubectl -n "$AI_NS" scale deploy/"$AI_DEPLOY" --replicas=0
trap 'echo "-- restoring ${AI_DEPLOY} --"; kubectl -n "$AI_NS" scale deploy/"$AI_DEPLOY" --replicas=1' EXIT

echo "-- waiting up to ${WAIT}s for the webhook receiver to log the alert --"
deadline=$(( $(date +%s) + WAIT ))
found=0
while [ "$(date +%s)" -lt "$deadline" ]; do
  if kubectl -n "$OBS_NS" logs -l app.kubernetes.io/component=alert-webhook-receiver --tail=200 2>/dev/null \
       | grep -q "InvForgeAIDown"; then
    found=1; break
  fi
  sleep 10
done

if [ "$found" -eq 1 ]; then
  echo "PASS: alert-webhook-receiver received InvForgeAIDown."
  kubectl -n "$OBS_NS" logs -l app.kubernetes.io/component=alert-webhook-receiver --tail=20 | grep "InvForgeAIDown" || true
else
  echo "FAIL: no InvForgeAIDown alert seen within ${WAIT}s."
  echo "  Alert timing = rule 'for: 1m' + AlertManager group_wait 10s. Check:"
  echo "    kubectl -n ${OBS_NS} logs -l app.kubernetes.io/component=alert-webhook-receiver"
  echo "    Prometheus /alerts (port-forward 9090)"
  exit 1
fi
