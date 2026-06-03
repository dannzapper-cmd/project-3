# Runbook — AlertManager test (PR-11B)

Validate the full alert loop end to end:
**metric → Prometheus rule → AlertManager → in-cluster webhook receiver → log.**

There is no external service, no Slack, no secrets. The receiver is a tiny
in-cluster Python server (`alert-webhook-receiver`) that logs each alert to
stdout, so `kubectl logs` is the proof.

## The three real rules

All use only verified PR-07 metrics (see `deploy/k8s/observability/templates/prometheus.yaml`):

1. **InvForgeAIDown** — `up{job="invforge-ai"} == 0` for 1m (critical)
2. **InvForgeDriftDetected** — `invforge_drift_detected == 1` for ~2 evaluations
3. **InvForgeArtifactMissing** — `invforge_artifact_available{artifact="decision_summary"} == 0` for 5m

## Automated end-to-end test (rule #1)

```bash
make obs-k8s-alert-test
```

This runs `deploy/k8s/observability/scripts/alert-test.sh`, which:

1. scales `deploy/invforge-ai-api` to 0 replicas in `invforge-ai` (real `up==0`);
2. waits up to 180s (rule `for: 1m` + AlertManager `group_wait: 10s`);
3. asserts the webhook receiver logged `InvForgeAIDown`;
4. restores the AI API to 1 replica (always, via trap).

Expected tail:

```
PASS: alert-webhook-receiver received InvForgeAIDown.
{"event": "alert_received", ..., "alerts": [{"alertname": "InvForgeAIDown", "severity": "critical", ...}]}
```

## Manual inspection

```bash
# Port-forward Prometheus + AlertManager (or use make obs-k8s-port-forward)
kubectl -n invforge-observability port-forward svc/prometheus 9090:9090 &
kubectl -n invforge-observability port-forward svc/alertmanager 9093:9093 &

# See rule state (pending -> firing) and active alerts
open http://localhost:9090/alerts
open http://localhost:9093

# Watch the receiver
kubectl -n invforge-observability logs -l app.kubernetes.io/component=alert-webhook-receiver -f
# or: make obs-k8s-logs
```

## Plugging in Slack/PagerDuty later

Edit `alertmanager.yml` (in `templates/alertmanager.yaml`): add a receiver with
the appropriate `slack_configs`/`pagerduty_configs` and point the route at it.
That requires a real credential/secret and an external service, so it is
**deferred** and intentionally not wired here (no secrets policy).
