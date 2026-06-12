# PR-14 / PR-15 Cloud Run live demo evidence

## Live read-only API (verified)

| Field | Value |
|-------|-------|
| Service | `invforge-ai-demo` |
| Region | `us-central1` |
| Project | `gen-lang-client-0873976301` |
| URL | https://invforge-ai-demo-lwcelvo7ya-uc.a.run.app |
| OpenAPI | https://invforge-ai-demo-lwcelvo7ya-uc.a.run.app/docs |

Env (from deploy template):

- `INVFORGE_ENV=cloud`
- `INVFORGE_DEMO_MODE=true`
- `INVFORGE_ALLOW_MUTATIONS=false`

Smoke: `make deploy-smoke BASE_URL=https://invforge-ai-demo-lwcelvo7ya-uc.a.run.app`

## Live read-only dashboard (PR-15)

| Field | Value |
|-------|-------|
| Service | `invforge-dashboard-demo` (activation-ready) |
| Image | `Dockerfile.dashboard` |
| URL | https://invforge-dashboard-demo-lwcelvo7ya-uc.a.run.app |
| Auth | `INVFORGE_DEMO_AUTH_ENABLED=true`, user `reviewer`, password `invforge-demo` |
| Verified | 2026-06-12 — login gate, read-only banner, quick links, sections 1–6 |
| Visual QA | 2026-06-12 — desktop + mobile login/dashboard pass; mermaid replaced with cards |
| Teardown | `DASHBOARD_SERVICE_NAME=invforge-dashboard-demo ./deploy/gcp/dashboard.teardown.example.sh` |

Deploy: see [`docs/cloud/gcp-cloud-run-activation.md`](../cloud/gcp-cloud-run-activation.md)

## Local validation evidence

Run on branch `cursor/pr15-live-dashboard-reviewer-ux`:

```bash
make reviewer-demo
make dashboard-smoke
make dashboard-docker-smoke
make test && make lint && make secrets-scan && make security-check && make deploy-validate
```

## Security posture

- No InvenTree core modifications
- No public MLflow/ZenML/InvenTree admin
- Cloud API mutations blocked (403)
- Dashboard demo auth is reviewer gate only
