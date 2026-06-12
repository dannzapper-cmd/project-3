# PR-12 - Full QA / Audit Report

Date: 2026-06-04  
Branch: `cursor/full-qa-audit-pr12`  
Audit start HEAD: `b818cbe` (PR-11B merge `01a5230` is an ancestor; `git merge-base --is-ancestor 01a5230 HEAD` -> `0`)  
Environment: Cursor Cloud Linux. Docker/kind/kubectl were unavailable. `uv`, Helm, and kubeconform were installed locally in the agent user environment to run static checks. No cloud resources were created.

## Scope audited

PR-01 through PR-11B were audited across repository reproducibility, Python tooling, Makefile targets, local/static Docker posture, API health/metrics, ML/MLOps/retraining, Kubernetes/Helm charts, observability, lineage, CI workflows, security/secrets, cloud deploy profiles, and documentation truthfulness.

Status vocabulary used literally: **PASS**, **FAIL**, **PARTIAL**, **NOT RUN**, **MANUAL REQUIRED**.

## PR-12 senior-review follow-up (2026-06-04)

- Retraining image reproducibility was fixed after review: `deploy/k8s/Dockerfile.retraining` now copies `pyproject.toml uv.lock ./` and runs `uv sync --frozen --no-dev --no-install-project --group ml --group retraining`. Runtime command/env behavior was not changed.
- GitHub Actions real CI is still required before merge: verify the PR checks in the GitHub UI after pushing this follow-up commit.
- Manual Mac validation is still required for Docker/kind/k8s/observability/lineage because Cursor Cloud does not provide Docker/kind/kubectl.

## Tagged classifications

### verified locally

- Current branch descends from PR-11B (`01a5230`) and contains `deploy/k8s/observability/` and `deploy/k8s/lineage/`.
- InvenTree is not vendored; `app/docker-compose.yml` uses official `inventree/inventree:${INVENTREE_TAG:-stable}` for server and worker.
- Python tooling is uv-based; `pyproject.toml` has dependency groups `dev`, `pipeline`, `ml`, `mlops`, `retraining`, `dashboard`, `observability`, `security`.
- `uv.lock` was missing/ignored at audit start; fixed by generating and tracking `uv.lock`, allowing Docker to use `uv sync --frozen`.
- Ruff, pytest, data determinism, validation, observability smoke, retraining smoke/check, security checks, Helm lint/template, kubeconform, deploy profile validation, workflow YAML parsing, and deploy-smoke unsafe-path self-check all ran locally after installing required static tools.
- Raw Helm templates are skipped from plain YAML parsing and validated through Helm render.
- Observability alert rules reference real metrics only: `up{job="invforge-ai"}`, `invforge_drift_detected`, and `invforge_artifact_available{artifact="decision_summary"}`.
- OpenLineage emission is env-gated: `OPENLINEAGE_URL` unset means no-op and no raise.

### inferred

- Docker image should now use the committed lockfile because `Dockerfile` copies `pyproject.toml uv.lock` and runs `uv sync --frozen`.
- Docker build and kind deployment are expected to follow previously merged PR-11A/11B paths, but this was not proven in Cursor Cloud because Docker/kind are unavailable.
- Trivy and SBOM are configured in `.github/workflows/security.yml`, but local binaries were not installed/run.

### NOT RUN

- `make docker-build-ai`, `make docker-smoke`, `docker compose ... config` real parse, `make docker-up`, local HTTP `/health`/`/metrics` against a running container, `make trivy-scan`, `make sbom`, live cloud deploy smoke, cosign signing workflow, SLA monitoring against a live URL.
- No `gcloud`, `aws`, or `az` commands were run.

### MANUAL REQUIRED

- Live Docker checks require Docker Desktop or equivalent.
- Live kind/kubernetes checks require Docker + kind + kubectl.
- Live PR-11B observability and lineage checks require a running kind cluster and port-forwards.
- Danny's Mac 8 GB can run the heavy stacks sequentially; a 16 GB VM is recommended only for combined screenshots or running compose + kind + observability + lineage together.

### blocked

- Cursor Cloud lacks Docker/kind/kubectl, so live Docker/k8s/observability/lineage validation was blocked by environment.
- Local Trivy/Syft scans were not run because the binaries are not installed; CI workflows cover those paths.

### out of scope

- Creating cloud resources; modifying InvenTree core; adding auth; OTEL-instrumenting the API; enabling BentoML blue/green E2E without a real image; Redis; Terraform; OpenMetadata; Mimir; final README/case-study/demo packaging.

## Coverage matrix (PR-01 -> PR-11B)

| PR | Area | Artifact/path | Status | How verified |
|----|------|---------------|--------|--------------|
| PR-01 | Base compose, synthetic data, CI skeleton | `app/docker-compose.yml`, `data/synthetic/`, `.github/workflows/ci.yml` | PARTIAL | Static inspection PASS; deterministic generation PASS; real Docker compose parse NOT RUN because Docker unavailable. |
| PR-02 | API sidecar, ingestion, validation, DVC/Feast skeleton | `api/`, `feast/`, `docs/runbooks/pr-02-data-pipeline.md` | PASS | `uv run pytest`; `make validate-data`; sidecar architecture verified. |
| PR-03 | ML baseline | `ml/train.py`, `ml/models/statsforecast_model.py`, model card | PASS | Tests PASS; `statsforecast_model.py` is referenced by `ml/train.py`, `ml/decision_intelligence.py`, and tests. |
| PR-04 | Decision intelligence | `ml/decision_intelligence.py`, `docs/decision-intelligence.md` | PASS | Tests PASS; docs corrected to keep synthetic-backtest caveats. |
| PR-05 | MLOps loop | `mlops/`, MLflow/Evidently/BentoML packaging paths | PARTIAL | Tests PASS; live MLflow UI/Bento image NOT RUN; BentoML serving remains templated/disabled. |
| PR-06 | Dashboard | `dashboard/`, `docs/dashboard.md` | PASS | Dashboard loader tests PASS; frontend/live browser NOT RUN. |
| PR-07 | Observability API | `observability/`, `/health`, `/metrics` code/tests | PASS | `uv run --group observability python -m observability.smoke` PASS; discovered and fixed metrics label guard bug. |
| PR-08 | Defensive security | `security/`, `.secrets.baseline`, `security.yml` | PASS | `make secrets-scan` PASS; `make security-check` PASS; tests PASS. |
| PR-09 | Retraining pipeline | `mlops/retraining/`, retraining docs | PASS | `make retrain-smoke` PASS; `make retraining-check` PASS; lineage unit tests PASS. |
| PR-10 | Deploy profiles | `Dockerfile`, `deploy/gcp`, `deploy/aws`, `deploy/azure`, `scripts/deploy_smoke.py` | PASS | `make deploy-validate` PASS; deploy-smoke unsafe-path guard PASS; cloud deploy NOT RUN. |
| PR-11A | Kubernetes AI layer | `deploy/k8s/helm/invforge`, `deploy/k8s/scripts` | PARTIAL | Helm lint/template/kubeconform PASS; live `k8s-up/deploy/smoke` MANUAL REQUIRED. |
| PR-11B | Observability + lineage | `deploy/k8s/observability`, `deploy/k8s/lineage`, ADR/runbooks | PARTIAL | Helm lint/template/kubeconform PASS; alert metrics and lineage gating verified statically; live `obs-k8s-*`/`lineage-*` MANUAL REQUIRED. |

## Command results

| Area | Command/check | Status | Evidence/notes | Follow-up |
|------|---------------|--------|----------------|-----------|
| baseline | `git status --short --branch`; `git log --oneline -n 20`; `git merge-base --is-ancestor 01a5230 HEAD` | PASS | Branch created from `main`; audit start HEAD `b818cbe`; PR-11B ancestor exit `0`. | None. |
| tooling availability | `command -v uv helm kubeconform docker kind kubectl trivy syft` | PARTIAL | Initially none were on PATH. Installed local `uv 0.11.19`, Helm `v3.16.4`, kubeconform `v0.6.7`. Docker/kind/kubectl/trivy/syft remained unavailable. | Use Danny Mac or configured agent image for live stack checks. |
| reproducibility | `uv lock`; `uv sync --frozen --group dev --group ml --group retraining` | PASS | `Resolved 276 packages`; frozen sync installed 154 packages. | Commit `uv.lock`; keep Docker frozen. |
| lint | `uv run ruff check .` | PASS | `All checks passed!` | None. |
| tests (CI groups) | `MLFLOW_ALLOW_FILE_STORE=true ZENML_ANALYTICS_OPT_IN=false uv run --group dev --group ml --group retraining pytest` | PASS | `145 passed, 9 skipped in 28.25s` before observability group was installed. | None. |
| aggregate CI before fix | `make ci` | FAIL | Failed `ml/tests/test_observability.py::test_metrics_have_no_path_label_values`; 150 passed, 3 skipped, 1 failed. Root cause: path-label guard treated allowlisted endpoint templates (`/health`, etc.) as filesystem paths once observability dependency was installed. | Fixed in `observability/metrics.py`; rerun passed. |
| targeted fix validation | `uv run pytest ml/tests/test_observability.py::test_metrics_have_no_path_label_values` | PASS | `1 passed in 0.03s`. | None. |
| aggregate CI after fix | `MLFLOW_ALLOW_FILE_STORE=true ZENML_ANALYTICS_OPT_IN=false make ci` | PASS | `151 passed, 3 skipped`; data validation PASS; `docker-config` printed `WARNING: docker not available; skipping compose config validation`; `CI checks passed.` | Real Docker compose config still MANUAL REQUIRED. |
| data determinism | generate seed 42 twice under `/tmp` and `diff -r` | PASS | Both runs generated 12 categories, 8 suppliers, 120 parts, 43,800 demand rows, 2,015 stock movements; `Deterministic output verified.` | None. |
| data validation | `make generate-data && make validate-data` | PASS | Synthetic CSVs validated; processed CSVs absent and skipped. | None. |
| observability smoke | `uv run --group observability python -m observability.smoke` | PASS | `observability-smoke: all checks passed.` | Live API `/metrics` smoke MANUAL REQUIRED. |
| retraining | `make retrain-smoke && make retraining-check` | PASS | Retraining completed; status `first_run_promoted`; artifacts under `artifacts/retraining`; check passed. MLflow emitted non-fatal `No module named pip` warnings under uv env. | Optional: consider adding pip to uv-created env only if warnings become operationally noisy. |
| deploy smoke guard | Python self-check for `_assert_safe_path` | PASS | `/health` allowed; `/v1/ingest/inventree`, `/retrain`, `/v1/model/rollback` blocked. | None. |
| workflow YAML | Python/PyYAML parse of `.github/workflows/*.yml` | PASS | `ci.yml`, `deploy.yml`, `security.yml`, `cosign-model-signing.yml`, `sla-monitoring.yml` parsed. | Check GitHub Actions UI after push. |
| Make target refs | Python scan of command-like `make <target>` docs refs vs Makefile targets | PASS | `All code-like make target references found in Makefile.` Actual parsed targets: 74. | None. |
| raw Helm regression | `_is_helm_raw_template(Path(...).resolve())` on AI/obs/lineage templates | PASS | All three sample templates returned `raw_helm_template=True`. | None. |
| Helm AI chart | `make helm-lint`; `helm template ... | kubeconform -summary -ignore-missing-schemas -` | PASS | `1 chart(s) linted, 0 failed`; kubeconform AI: `8 resources ... Valid: 8`. | Live kind MANUAL REQUIRED. |
| Helm observability chart | `make obs-k8s-lint`; `helm template ... | kubeconform ...` | PASS | `1 chart(s) linted, 0 failed`; kubeconform obs: `29 resources ... Valid: 29`. | Live obs profile MANUAL REQUIRED. |
| Helm lineage chart | `make lineage-lint`; `helm template ... | kubeconform ...` | PASS | `1 chart(s) linted, 0 failed`; kubeconform lineage: `7 resources ... Valid: 7`. | Live lineage profile MANUAL REQUIRED. |
| deploy profiles | `make deploy-validate` | PASS | `Deploy profile validation PASSED (66 deploy files checked).` | None. |
| security secrets | `make secrets-scan` | PASS | detect-secrets baseline scan passed. Baseline has known test placeholders and local Grafana admin/admin hash only. | None. |
| security checks | `make security-check` | PASS | Bandit PASS, pip-audit PASS (`No known vulnerabilities found`), detect-secrets PASS. | Local Trivy/Syft NOT RUN. |
| secret pattern search | regex scan for `API_KEY=`, `SECRET=`, `TOKEN=`, `PASSWORD=`, private keys, kubeconfig, AWS/GCP credential hints | PASS | No suspicious matches outside ignored lockfile scope. | Continue baseline scans in CI. |
| Docker compose config | `make docker-config` | NOT RUN | Target printed `WARNING: docker not available; skipping compose config validation` and exited 0; no real compose parse occurred. | Run on Docker host. |
| Docker build/smoke | `make docker-build-ai`; `make docker-smoke`; `make k8s-retrain-image` | MANUAL REQUIRED | Docker unavailable in Cursor Cloud. Static Dockerfile review confirms root and retraining images now use `uv.lock` + `uv sync --frozen`. | Run on Danny Mac. |
| kind/k8s live | `make k8s-preflight/up/deploy/status/smoke/down`; `kubectl get pods -A` | MANUAL REQUIRED | Docker/kind/kubectl unavailable. Static Helm validation passed. | Run sequentially on Danny Mac. |
| PR-11B live obs | `make obs-k8s-up/status/port-forward/smoke/alert-test/down` | MANUAL REQUIRED | Requires kind cluster and ~2 GB observability profile. Static chart validation passed. | Run after baseline k8s teardown if RAM-constrained. |
| lineage live | `make lineage-up/port-forward/smoke/down` | MANUAL REQUIRED | Danny Mac found `marquez-api` CrashLoopBackOff before this follow-up. Root cause fixed in chart config; live rerun still required because Cursor lacks Docker/kind/kubectl. | Run last; wait for all lineage deployments available before smoke. |
| cloud deploy | GCP/AWS/Azure commands | NOT RUN | No cloud CLIs or resource-mutating commands were run. READMEs/templates inspected; deploy validator passed. | Explicit human cloud decision required. |
| trivy/sbom local | `make trivy-scan`; `make sbom` | NOT RUN | `trivy`/`syft` binaries unavailable locally. Workflows are configured in `security.yml`. | Check GitHub Actions after push or install local binaries. |

## Findings and minimal hardening applied

### F0 - PR-12 follow-up: Marquez API CrashLoopBackOff in lineage profile (fixed statically; live rerun manual)

- Before (Danny Mac manual validation): `make lineage-up` installed the chart and `marquez-db` / `marquez-web` reached `1/1 Running`, but `marquez-api` entered `0/1 CrashLoopBackOff`; `make lineage-smoke` failed because `http://localhost:5000` was unreachable. Logs showed `WARNING 'MARQUEZ_CONFIG' not set, using development configuration.`
- Root cause: Marquez 0.49.0's bundled `marquez.dev.yml` hardcodes the database host as `postgres`. The InvForge chart's Postgres Service is `marquez-db`, and the chart's `POSTGRES_HOST=marquez-db` env var was ignored by the bundled development config. The API therefore attempted DB startup/migration against the wrong host and exited.
- Fix: `deploy/k8s/lineage/templates/marquez.yaml` now renders a `marquez-api-config` ConfigMap with an explicit Kubernetes `marquez.yml`, sets `MARQUEZ_CONFIG=/etc/marquez/marquez.yml`, and mounts the config into the API pod. The config uses `${POSTGRES_HOST:-marquez-db}` plus the existing `POSTGRES_*` env vars. No Marquez version change, new database architecture, or feature expansion.
- Static rerun: `make lineage-lint` PASS; `helm template invforge-lineage deploy/k8s/lineage -n invforge-lineage` PASS; `python3 scripts/validate_deploy_profiles.py` PASS (`python` binary is unavailable in Cursor, so `python3` was used for the same script); `uv run ruff check .` PASS; `uv run pytest` PASS (`151 passed, 3 skipped`).
- Live status: MANUAL REQUIRED in Cursor because Docker/kind/kubectl are unavailable. Danny should rerun `make lineage-up`, `kubectl wait --for=condition=available deployment --all -n invforge-lineage --timeout=300s`, `make lineage-status`, `make lineage-port-forward`, `make lineage-smoke`, then `make lineage-down`.


### F1 - Reproducibility gap: missing tracked `uv.lock` (fixed)

- Before: `uv.lock` was not tracked and `.gitignore`/`.dockerignore` excluded it, despite uv being the project package manager.
- Root cause: repository treated the uv lockfile like local metadata, so Docker and local installs resolved dependencies from `pyproject.toml` alone.
- Fix: generated `uv.lock`, stopped ignoring it, allowed Docker build context to include it, changed the root Docker build to `uv sync --frozen --no-dev --no-install-project --group observability`, and changed the retraining Docker build to `uv sync --frozen --no-dev --no-install-project --group ml --group retraining`.
- After: `uv sync --frozen --group dev --group ml --group retraining` passed; both Dockerfiles now consume the lockfile.

### F2 - Observability metric path-label guard false positive (fixed)

- Before: after installing the observability group, `make ci` failed because `assert_no_path_label_values()` flagged normalized endpoint labels such as `/health` as paths.
- Root cause: the guard did not distinguish allowlisted API endpoint templates from filesystem paths.
- Fix: allow `label_name == "endpoint"` when the value is one of `KNOWN_ENDPOINTS`; still flag slashes/backslashes elsewhere.
- After: targeted test passed; full `make ci` passed with 151 passed / 3 skipped.

### F3 - Documentation overclaims/stale status (fixed minimally)

- README, master context, deployment contract, k8s README, ADR/runbooks, cloud READMEs, model card, and app README had stale PR-02/PR-11B/future wording or overclaims.
- Fixes were limited to truthful status/scope corrections: no README packaging rewrite, no case study, no demo narrative work.

### F4 - Live stack validation blocked by environment (documented)

- Docker/kind/kubectl unavailable in Cursor Cloud.
- Static alternatives passed (Helm/kubeconform/deploy validation), but live Docker/k8s/obs/lineage checks remain MANUAL REQUIRED.

## Security / secrets findings

- No new committed secret pattern found by direct regex scan.
- `make secrets-scan` passed against `.secrets.baseline`.
- During audit, detect-secrets surfaced local-only chart placeholder passwords (`admin` for Grafana and `marquez` for ephemeral Postgres). They were remediated with explicit `# pragma: allowlist secret` comments in the chart values rather than expanding `.secrets.baseline`.
- `.secrets.baseline` remains limited to the known/expected local/test placeholders: API test credentials and the PR-07 local Grafana admin/admin entry.
- `make security-check` passed: Bandit, pip-audit, detect-secrets.
- Secret manifests are placeholders only (`<CHANGE_ME>` in Helm values/Secret template).
- Cloud profile env examples use placeholders only; deploy validator passed forbidden-pattern scans.
- Mutation endpoint `POST /v1/ingest/inventree` remains blocked by default in demo/cloud mode; deploy smoke refuses unsafe paths.

## Kubernetes / Helm posture

Verified statically:

- AI API resources: requests `50m/128Mi`, limits `500m/256Mi`; liveness/readiness `/health`; non-root UID 10001; read-only root filesystem; drop all caps; seccomp RuntimeDefault.
- ConfigMap and Secret templates exist; Secret values are placeholders.
- NetworkPolicy exists and is documented as structural-only on kindnet.
- Retraining Job and CronJob templates exist; `backoffLimit: 0`; CronJob is suspended by default; separate retraining image.
- BentoML/blue-green templates exist but are disabled until a real Bento image is built.
- Observability chart renders Prometheus/Grafana/Loki/Tempo/OTel/AlertManager/webhook receiver; alert rules use real metrics.
- Lineage chart renders Marquez + ephemeral Postgres; local/dev only.

Not verified live:

- Pod readiness, port-forward `/health` and `/metrics`, alert loop, and Marquez UI/API smoke require Docker/kind/kubectl.

## Observability / lineage honesty

- Demo/cloud `/health` returns HTTP 200 even when artifact payload says `unavailable`; audit/docs now explicitly require inspecting the JSON body (`artifacts`, `champion_challenger_decision`) rather than status code only.
- `/metrics` contract is verified by tests and observability smoke; endpoint label guard fixed.
- OTel Collector + Tempo are deployed as idle OTLP backends; API is not OTEL-instrumented and traces are not faked.
- Lineage is a hard no-op unless `OPENLINEAGE_URL` is set; errors never break retraining.
- `make lineage-smoke` remains MANUAL REQUIRED because it needs Marquez up and port-forwarded.

## Cloud/deploy readiness

- `deploy/gcp`, `deploy/aws`, `deploy/azure` are templates/runbooks, not live deployments.
- `make deploy-validate` passed: placeholders, syntax, no real-looking secrets, per-provider README teardown coverage, Docker ignore coverage, Helm render/kubeconform.
- No cloud resources were created. No `gcloud`, `aws`, or `az` commands were run.
- Cost and teardown docs exist and warn about provider billing and cleanup.

## Laptop 8 GB constraints

- Do not co-run InvenTree Compose, baseline kind, observability, and lineage.
- Recommended sequence on 8 GB: Docker layer -> tear down -> k8s AI layer -> tear down -> observability -> tear down -> lineage -> tear down.
- A temporary 16 GB VM is recommended only if combined screenshots require multiple heavy stacks simultaneously.

## Manual validation plan for Danny (Mac, 8 GB)

Run one heavy layer at a time and paste command output into this report or PR notes:

```bash
git rev-parse --short HEAD
uv run ruff check .
uv run pytest
make deploy-validate
make helm-lint && make helm-template
make obs-k8s-lint && make obs-k8s-template && make lineage-lint
make secrets-scan
make security-check
make retrain-smoke
make retraining-check

make docker-config
make docker-build-ai
make docker-smoke
make docker-down

make k8s-preflight
make k8s-up && make k8s-deploy && make k8s-status && make k8s-smoke
kubectl get pods -A
make k8s-down

make obs-k8s-up && make obs-k8s-status
make obs-k8s-smoke && make obs-k8s-alert-test
make obs-k8s-down

make lineage-up && make lineage-port-forward
make lineage-smoke
make lineage-down
```

If any live stack OOMs or CrashLoops on 8 GB, stop the stack, capture `kubectl describe`/logs, and rerun on a 16 GB VM.

## Blocker list (must fix before PR-13)

No repository blocker remains from static/local PR-12 validation.

Manual evidence still required before final PR-13 packaging claims:

1. Docker image build/smoke on a Docker host.
2. Live kind AI layer smoke (`/health` body and `/metrics`, not just status 200).
3. Live observability smoke and alert loop.
4. Live lineage smoke with Marquez.
5. GitHub Actions real CI status after this branch is pushed (CI, Deploy Validation, Security) is required before merge.

## Gap list (acceptable, documented)

- No live cloud deployment; cloud profiles are templates only.
- BentoML blue-green E2E disabled until a Bento image exists.
- OTel/Tempo traces idle until future API instrumentation.
- NetworkPolicy is structural-only on default kindnet.
- Trivy/Syft local scans not run; workflow coverage configured.
- MLflow emitted non-fatal `No module named pip` warnings during retraining smoke under uv; command passed.
- No auth/security rewrite; mutation guard remains the PR-10 safety mechanism.

## Safe for PR-13 packaging?

**Yes with minor caveats.** Static/local validation is materially stronger after PR-12 hardening, but PR-13 should not claim live Docker/k8s/observability/lineage success until Danny captures the manual evidence above. Any screenshots/demo narrative must label synthetic data and activation-ready cloud profiles honestly.

## Files changed in PR-12

- `.gitignore` - allow `uv.lock` to be tracked.
- `.dockerignore` - allow `uv.lock` into Docker build context.
- `uv.lock` - committed reproducibility lockfile.
- `Dockerfile` - copy `uv.lock`; use `uv sync --frozen`.
- `deploy/k8s/Dockerfile.retraining` - copy `uv.lock`; use frozen uv sync for `ml` + `retraining` groups.
- `observability/metrics.py` - fix endpoint-label path guard.
- `README.md` - minimal stale-status/scope corrections.
- `PROJECT_3_INVFORGE_MASTER_CONTEXT.md` - minimal corrections to current status and overclaims.
- `CONTRIBUTING.md` - correct `make ci` description.
- `app/README.md` - clarify sidecar services remain outside base compose.
- `docs/observability.md` - document demo/cloud health status caveat.
- `docs/deployment-contract.md` - refresh PR-10 vs PR-11A/11B scope.
- `deploy/k8s/README.md` - refresh optional PR-11B status.
- `deploy/k8s/observability/values.yaml`, `deploy/k8s/lineage/values.yaml` - explicitly allowlist documented local-only placeholder passwords.
- `docs/adr/002-pr11a-kubernetes-scope.md`, `docs/runbooks/k8s-startup.md`, `docs/runbooks/retraining-manual-trigger.md` - replace stale PR-11B deferral wording.
- `deploy/gcp/README.md`, `deploy/aws/README.md`, `deploy/azure/README.md` - clarify local kind vs managed cloud Kubernetes.
- `docs/model-cards/demand_forecast_baseline.md` - update PR-10/11 status and future benchmark notes.
- `docs/audits/pr12-full-qa-audit.md` - this audit report.
- `deploy/k8s/lineage/templates/marquez.yaml` - explicit Marquez Kubernetes config to avoid dev-config DB host mismatch.
- `docs/runbooks/lineage-inspection.md` - CrashLoopBackOff troubleshooting note.
