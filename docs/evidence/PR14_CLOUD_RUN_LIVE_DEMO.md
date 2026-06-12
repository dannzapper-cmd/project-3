# PR-14 / PR-15 — Live Cloud Run demo evidence

Date: 2026-06-12
Label: **Live Cloud Run portfolio demo** — read-only API + reviewer dashboard. Not production.

## Summary

| Phase | Scope |
|-------|-------|
| **PR-14** | Live read-only AI Operations API on Cloud Run |
| **PR-15 / PR #21** | Live read-only Streamlit dashboard + reviewer UX hardening |

Dashboard, MLflow, ZenML, InvenTree core, retraining, and Kubernetes profiles
remain **local-only** except the fixture-backed cloud dashboard surface.

---

## Live read-only API (PR-14, verified)

| Field | Value |
|-------|-------|
| Service | `invforge-ai-demo` |
| Region | `us-central1` |
| Project | `gen-lang-client-0873976301` |
| URL | https://invforge-ai-demo-lwcelvo7ya-uc.a.run.app |
| OpenAPI | https://invforge-ai-demo-lwcelvo7ya-uc.a.run.app/docs |

### Container environment

| Variable | Value |
|----------|-------|
| `INVFORGE_ENV` | `cloud` |
| `INVFORGE_DEMO_MODE` | `true` |
| `INVFORGE_ALLOW_MUTATIONS` | `false` |
| `LOG_LEVEL` | `INFO` |

No secrets, tokens, or credentials were committed or required.

### Deploy commands used (PR-14)

```bash
export PROJECT_ID="gen-lang-client-0873976301"
export REGION="us-central1"
export IMAGE="us-central1-docker.pkg.dev/${PROJECT_ID}/cloud-run-source-deploy/invforge-ai-demo:latest"

gcloud builds submit --tag "$IMAGE" --project "$PROJECT_ID" .

gcloud run deploy invforge-ai-demo \
  --image "$IMAGE" \
  --region "$REGION" \
  --project "$PROJECT_ID" \
  --allow-unauthenticated \
  --set-env-vars INVFORGE_ENV=cloud,INVFORGE_DEMO_MODE=true,INVFORGE_ALLOW_MUTATIONS=false,LOG_LEVEL=INFO \
  --max-instances 1 \
  --min-instances 0 \
  --memory 512Mi \
  --cpu 1
```

### API live endpoints

| Endpoint | Result |
|----------|--------|
| `GET /health` | HTTP 200 — artifacts missing (expected on fresh container) |
| `GET /metrics` | HTTP 200 — Prometheus text |
| `GET /v1/inventory/status` | HTTP 200 — `allow_mutations: false` |
| `GET /v1/data/summary` | HTTP 200 — empty local data |
| `POST /v1/ingest/inventree` | **HTTP 403** — mutation blocked |

### API smoke commands

```bash
export SERVICE_URL="https://invforge-ai-demo-lwcelvo7ya-uc.a.run.app"

bash scripts/cloud_run_smoke.sh
make deploy-smoke BASE_URL="$SERVICE_URL"

curl -fsS "$SERVICE_URL/health"
curl -fsS "$SERVICE_URL/metrics" | head -n 30
curl -i -X POST "$SERVICE_URL/v1/ingest/inventree"   # expect 403
```

---

## Live read-only dashboard (PR-15 / PR #21)

| Field | Value |
|-------|-------|
| Service | `invforge-dashboard-demo` |
| Image | `Dockerfile.dashboard` |
| URL | https://invforge-dashboard-demo-lwcelvo7ya-uc.a.run.app |
| Auth | `INVFORGE_DEMO_AUTH_ENABLED=true`, user `reviewer`, password `invforge-demo` |
| Verified | 2026-06-12 — login gate, read-only banner, quick links, sections 1–6 |
| Visual QA | 2026-06-12 — desktop + mobile login/dashboard pass; mermaid replaced with cards |

Deploy: [`docs/cloud/gcp-cloud-run-activation.md`](../cloud/gcp-cloud-run-activation.md)

Teardown: `DASHBOARD_SERVICE_NAME=invforge-dashboard-demo ./deploy/gcp/dashboard.teardown.example.sh`

### Dashboard smoke

```bash
curl -I https://invforge-dashboard-demo-lwcelvo7ya-uc.a.run.app/_stcore/health
make dashboard-docker-smoke
```

---

## What is live vs local-only

| Component | Live on Cloud Run? |
|-----------|-------------------|
| AI Operations API (read-only) | **Yes** |
| Streamlit dashboard (fixture-backed) | **Yes** |
| InvenTree core | No — not deployed |
| MLflow / ZenML / retraining | No — local only |
| kind Kubernetes profiles | No — local only |

---

## Local validation evidence (PR #21)

```bash
make reviewer-demo
make dashboard-smoke
make dashboard-docker-smoke
make test && make lint && make secrets-scan && make security-check && make deploy-validate
```

---

## Screenshots

| File | Source |
|------|--------|
| `cloud-run-health.png` | API `/health` JSON |
| `cloud-run-docs.png` | API `/docs` |
| `cloud-run-mutation-blocked.png` | POST ingest 403 curl output |

---

## Cost warning and guardrails

Charges may apply for Cloud Run request/CPU time, Cloud Build minutes, Artifact
Registry storage, and logs. Low-traffic demo with scale-to-zero can stay
low-cost, but **watch billing** in the GCP console.

| Guardrail | Setting |
|-----------|---------|
| Scale to zero | `min-instances: 0` |
| Cap burst | `max-instances: 1` |
| Resources | 512Mi RAM, 1 CPU — no GKE, no VM, no managed DB, no Redis, no load balancer |
| Portfolio use | Keep live **only during job-search**; delete when no longer needed |

## Teardown

```bash
./deploy/gcp/dashboard.teardown.example.sh
gcloud run services delete invforge-ai-demo --region us-central1
```

Optionally delete Artifact Registry repositories if images are no longer needed.

## Security confirmations

- No secrets committed
- No cloud credentials committed
- No InvenTree core deployed
- Not production
- No multi-cloud live claim
- Dashboard demo auth is reviewer gate only
- Cloud API mutations blocked (403)
