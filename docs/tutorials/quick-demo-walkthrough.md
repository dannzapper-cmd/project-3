# Quick demo walkthrough (5 / 15 / 30 minutes)

## 5 minutes — browser only

1. Open live API docs: https://invforge-ai-demo-lwcelvo7ya-uc.a.run.app/docs
2. Execute `GET /health` — expect HTTP 200
3. Execute `GET /v1/inventory/status` — read-only config summary
4. Confirm `POST /v1/ingest/inventree` is blocked (403) in cloud mode
5. (When dashboard is live) open https://invforge-dashboard-demo-lwcelvo7ya-uc.a.run.app and sign in (`reviewer` / `invforge-demo`)

## 15 minutes — local dashboard

```bash
uv sync --group dev --group pipeline --group ml --group mlops --group dashboard
make reviewer-demo
make dashboard
```

Open http://localhost:8501 and walk through sections 1–4.

## 30 minutes — local + API + samples

After the 15-minute path:

```bash
make observability-api   # terminal 2
curl http://localhost:8001/health
curl http://localhost:8001/metrics
```

Review sample inputs:

- `examples/demo-scenario/scenario.yaml`
- `examples/api/forecast_request.json`

Full guide: [`REVIEWER_DEMO_GUIDE.md`](REVIEWER_DEMO_GUIDE.md)
