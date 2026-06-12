# PR-12.6 — Senior QA + Usable Demo + Deployment Readiness

Date: 2026-06-11 (hardening pass)  
Repo: `/Users/danny/project-3-clean`  
Branch: `cursor/pr12-6-senior-qa-usable-demo`  
HEAD: `2502e73872776c758236dbedf2f6746fd4e965aa` (unchanged — working tree has PR-12.6 deliverables)  
Prior audit: `docs/audits/pr12-full-qa-audit.md`

## Hardening pass summary

This report reflects the **final hardening pass** after the initial PR-12.6 delivery.
Gaps closed: kubeconform install, Trivy/SBOM local runs, combined
`obs-k8s-alert-test` (AI + observability), collector `--observability-combined`,
tutorial clarifications (p10/p50/p90, stockout risk, tool roles), Makefile trivy
skip-dirs for local `.venv`/`mlruns` (matches CI checkout scope).

## Tool availability (final)

| Tool | Status |
|------|--------|
| uv | Installed |
| Docker Desktop | Available |
| kind / kubectl / helm | Installed |
| kubeconform 0.8.0 | Installed via Homebrew |
| trivy 0.71.1 | Installed via Homebrew |
| syft 1.45.1 | Installed via Homebrew |

## Final validation table

| Check | Status | Notes |
|-------|--------|-------|
| Ruff | **PASS** | `uv run ruff check .` |
| Pytest | **PASS** | 154 passed |
| uv lock | **PASS** | `uv lock --check` |
| deploy-validate (+ kubeconform) | **PASS** | 66 deploy files; no kubeconform warnings |
| helm lint/template | **PASS** | via static collector |
| obs chart lint/template | **PASS** | |
| lineage chart lint | **PASS** | |
| secrets-scan | **PASS** | |
| security-check | **PASS** | bandit, pip-audit, detect-secrets |
| demo-local | **PASS** | prior + post-fix runs |
| Docker build/smoke | **PASS** | `docs/evidence/pr12-6-local/20260611-230829/` |
| kind AI layer | **PASS** | `docs/evidence/pr12-6-local/20260611-230900/` |
| observability smoke | **PASS** | with pod-ready wait |
| observability alert-test | **PASS** | combined run; webhook logged `InvForgeAIDown` |
| lineage smoke | **PASS** | Marquez `invforge.retraining`; `20260611-231321/` |
| Trivy | **PASS** | `uv.lock` clean; skips local `.venv`/`mlruns` |
| SBOM | **PASS** | `artifacts/security/sbom.cyclonedx.json` (gitignored) |
| Cloud deploy | **NOT RUN** | Template-only by design; no credentials |
| GitHub Actions | **MANUAL REQUIRED AFTER PUSH** | Branch not pushed at time of report |

## Combined observability alert test

Evidence: `docs/evidence/pr12-6-local/20260611-233122/`

Sequence: `k8s-up` → `k8s-deploy` → `k8s-smoke` → `obs-k8s-up` → port-forward →
`obs-k8s-smoke` → `obs-k8s-alert-test` → teardown.

Alert webhook received:

```json
{"event": "alert_received", "alerts": [{"status": "firing", "alertname": "InvForgeAIDown", "severity": "critical"}]}
```

Collector flag: `bash scripts/collect_pr12_6_evidence.sh --observability-combined`

## What was fixed in hardening pass

1. **kubeconform** — installed; deploy-validate no longer PARTIAL
2. **Trivy/SBOM** — tools installed; `make trivy-scan` updated to skip local
   `.venv`/`mlruns` (CI scans clean checkout; avoids feast transitive yarn.lock noise)
3. **obs-k8s-alert-test** — run with AI layer deployed; **PASS**
4. **Collector** — `--observability-combined`; trivy/sbom in `--static`; kubeconform in tools.txt
5. **Tutorials** — p10/p50/p90, stockout risk, MLflow/Evidently/ZenML/BentoML roles, combined obs sequence

## Remaining items (honest)

| Item | Status |
|------|--------|
| GitHub Actions CI on this branch | MANUAL REQUIRED AFTER PUSH |
| Browser Streamlit walkthrough | Optional manual |
| BentoML blue/green k8s E2E | Out of PR-12.6 scope (templated) |
| Live Cloud Run deploy | NOT RUN (template-only) |

## Security confirmations

- No secrets committed in PR-12.6 deliverables
- No cloud credentials used
- No cloud resources created
- InvenTree core not modified
- Mutation endpoints blocked in demo/cloud mode (`INVFORGE_ENV=demo`)
- Trivy CRITICAL on `uv.lock`: 0 (with standard skip-dirs for local caches)

## Usability deliverables

| Artifact | Path |
|----------|------|
| Quick demo | `docs/tutorials/quick-demo-walkthrough.md` |
| Backend/ML explainer | `docs/tutorials/backend-and-ml-explainer.md` |
| Demo scenario | `examples/demo-scenario/` |
| Sample API JSON | `examples/api/sample_*.json` |
| Evidence collector | `scripts/collect_pr12_6_evidence.sh` |
| Convenience target | `make demo-local` |

## PR-13 readiness verdict

**PARTIALLY READY**

All local senior QA gates pass including combined alert-test, kubeconform,
Trivy, and SBOM. PR-13 final packaging should proceed after **push + green GitHub
Actions** on this branch. No blockers remain in local validation.

## Exact next action

```bash
cd /Users/danny/project-3-clean
git add -A
git commit -m "PR-12.6: senior QA hardening, tutorials, evidence collector"
git push -u origin cursor/pr12-6-senior-qa-usable-demo
# Verify GitHub Actions in the PR UI
```

## Evidence folders (gitignored logs)

| Run | Path |
|-----|------|
| Static (final) | `docs/evidence/pr12-6-local/20260611-233943/` |
| Docker | `docs/evidence/pr12-6-local/20260611-230829/` |
| k8s | `docs/evidence/pr12-6-local/20260611-230900/` |
| Observability combined + alert | `docs/evidence/pr12-6-local/20260611-233122/` |
| Lineage | `docs/evidence/pr12-6-local/20260611-231321/` |
