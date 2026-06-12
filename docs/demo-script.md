# InvForge demo script (reviewer-facing)

Use this script when presenting InvForge in a portfolio review or live walkthrough.

## Opening (30 seconds)

> InvForge is an AI Operations sidecar on InvenTree. The cloud demo is **read-only**
> with **synthetic data**. The full ML/MLOps pipeline runs locally. We do not claim
> real-world savings — cost figures are simulated backtest diagnostics.

## Path A — Live cloud (no install)

1. **API docs:** https://invforge-ai-demo-lwcelvo7ya-uc.a.run.app/docs
2. Run `GET /health` — show artifact flags and read-only posture
3. Run `GET /v1/inventory/status`
4. Show `POST /v1/ingest/inventree` returns 403
5. **Dashboard:** https://invforge-dashboard-demo-lwcelvo7ya-uc.a.run.app
   - Sign in: `reviewer` / `invforge-demo`
   - Point out read-only banner
   - Walk Overview → Forecast → Decision → MLOps

## Path B — Full local

```bash
make reviewer-demo && make dashboard
```

Highlight:

- Deterministic seed 42 synthetic data
- Champion/challenger comparison chart
- Top reorder recommendations table
- MLOps drift/registry summary

## Sample inputs to mention

- `examples/demo-scenario/scenario.yaml`
- `examples/api/forecast_request.json`

## Closing limitations

- InvenTree, MLflow, ZenML: local only
- No mutation/admin in cloud
- Demo auth is not production security

Guide: [`REVIEWER_DEMO_GUIDE.md`](REVIEWER_DEMO_GUIDE.md)
