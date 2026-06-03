# Deployment Security — InvForge AI Operations Layer (PR-10)

Security contract for deploying the external AI Operations Layer. Read alongside
`docs/deployment-contract.md` (endpoint classification) and the PR-08 security
layer (unchanged by PR-10).

## 1. No secrets in the repo

- No real tokens, passwords, project/account/subscription IDs, billing
  identifiers, or keys are committed. All deploy templates use **placeholders
  only**.
- `.dockerignore` prevents leaking `.env*`, `mlruns/`, `artifacts/`, `data/`,
  `notebooks/`, `.git/`, `__pycache__/`, `.secrets.baseline`, and `.venv/` into
  the runtime image.
- `detect-secrets` (PR-08) remains in CI via `.secrets.baseline`; a
  `validate_deploy_profiles.py` check additionally scans deploy files and
  `*.env.example` for real-looking secret patterns.

## 2. Env vars vs secrets

| Category | Examples | Where it goes |
|----------|----------|---------------|
| **Plain config** (non-sensitive) | `INVFORGE_ENV`, `INVFORGE_DEMO_MODE`, `PORT`, `LOG_LEVEL`, `INVFORGE_DATA_DIR` | Inline as provider env vars (service YAML / task def) |
| **Secret** (credentials/tokens/URLs with passwords) | `INVENTREE_API_TOKEN`, `INVENTREE_PASSWORD`, any DB URL with credentials | Provider **secret store** only (see §3); referenced by name/ARN |
| **Must NEVER appear on a public demo** | `INVFORGE_ALLOW_MUTATIONS=true`, MLflow registry write access, retraining mutation flags | Not set on cloud/demo at all |

The default read-only demo surface needs **no secrets** — secrets are only
required if you deliberately enable live InvenTree ingestion (mutations).

## 3. Provider secret stores (conceptual)

- **GCP:** Secret Manager → referenced via `secretKeyRef` in the Cloud Run
  service (commented example in `deploy/gcp/service.template.yaml`).
- **AWS:** Secrets Manager → referenced via the task definition `secrets` block
  (`valueFrom` ARN) in `deploy/aws/ecs-fargate-task-definition.template.json`.
- **Azure:** Container Apps secrets / Key Vault → referenced via `secretRef` in
  `deploy/azure/container-app.template.yaml`.

The templates show the reference **pattern** with placeholder names/ARNs only.

## 4. Public demo is read-only

- Cloud/demo mode defaults to `INVFORGE_ALLOW_MUTATIONS=false`. The only UNSAFE
  endpoint (`POST /v1/ingest/inventree`) returns **HTTP 403** and performs no
  work. This is enforced in code and covered by tests
  (`api/tests/test_api.py::test_cloud_mode_blocks_mutation_endpoint`).
- There is **no public retraining mutation** by default (no such endpoint exists
  in the deployable API).

## 5. MLflow / ZenML are not production secret stores

`mlruns/` (MLflow) and the ZenML local SQLite/file stack are **local developer
state**, not secret stores and not publicly exposed. No deployable endpoint
proxies MLflow or ZenML state; both remain local-only (run via `make` targets).

## 6. CORS / exposure

- The AI Operations API does **not** currently configure CORS middleware. The
  deployed surface is read-only (mutations blocked), so an absent/open CORS
  policy does not expose a mutation risk in PR-10.
- **Before any non-demo deployment**, lock CORS down: allow only the dashboard
  origin (or specific trusted origins) rather than `*`, and never combine `*`
  with credentialed or mutating endpoints. Do not enable mutation endpoints
  publicly without an authn/authz gate first.

## 7. Network / WAF posture

- WAF/DDoS protection is provided as **activation-ready templates** only
  (Cloud Armor / AWS WAF / Azure Front Door WAF). It is **not active** until you
  deploy it with a provider account and a public load-balancer/Front Door
  entrypoint. See each profile README.
- The container runs as a **non-root** user (`appuser`, uid 10001) and exposes
  only the HTTP port.

## 8. PR-08 security checks remain in CI

The `Security` workflow (Bandit, pip-audit, detect-secrets, security pipeline +
smoke + tests, Trivy, SBOM) is unchanged. PR-10 adds **no offensive security
features** and does not weaken any existing check. New Python code (the runtime
mode gate, smoke, and validation scripts) is covered by Bandit's existing scan of
`api/`.
