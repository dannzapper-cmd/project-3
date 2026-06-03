# SLA / Uptime Monitoring Hooks (PR-10)

Lightweight, read-only uptime monitoring hooks for a deployed InvForge AI
Operations demo surface. This is **portfolio/demo uptime monitoring, not a
contractual SLA**.

## What is monitored

When a public demo URL is configured, the read-only smoke probe
(`scripts/deploy_smoke.py`) checks:

- `GET /health` → HTTP 200 with a JSON body containing `status` and `pr_stage`
  (required).
- `GET /v1/inventory/status` → HTTP 200 (optional; reports `env`/mode).
- `GET /v1/data/summary` → HTTP 200 (optional).

## What is NOT monitored

- No latency SLO, error-budget, or alerting/paging.
- No mutation, retraining, rollback, promotion, registry, audit, or scan calls
  (the probe refuses these paths in code).
- No authentication or per-tenant monitoring.
- No synthetic transaction beyond the read-only GETs above.

## How to configure a public demo URL later

1. Deploy the AI Operations API to a provider (see `deploy/gcp|aws|azure`).
2. Add the public URL as a repository **variable** named `DEMO_BASE_URL`
   (Settings → Secrets and variables → Actions → Variables). A non-secret URL is
   fine as a variable; use a secret only if the URL itself must stay private.
3. Run the **SLA Monitoring** workflow:
   - Manually via **workflow_dispatch** (always available), optionally passing a
     `base_url` input that overrides the variable.
   - Or enable the optional `schedule` block in
     `.github/workflows/sla-monitoring.yml`.

If `DEMO_BASE_URL` is not configured and no input is given, the workflow **skips
gracefully** (it does not fail). This keeps the default repo green with no live
deployment.

## Local usage

```bash
# Against a locally running API (make observability-api in another shell):
make deploy-smoke BASE_URL=http://localhost:8001
# or directly:
python scripts/deploy_smoke.py --base-url http://localhost:8001
```

## Limitations

- Requires a reachable public URL; no URL ⇒ no monitoring (workflow skips).
- GitHub Actions `schedule` is best-effort and may be delayed/skipped on busy
  runners; it is **not** a guaranteed heartbeat.
- This does not replace provider-native uptime checks (e.g. Cloud Monitoring
  uptime checks, CloudWatch Synthetics, Azure Monitor) — those are deferred to
  production hardening.
