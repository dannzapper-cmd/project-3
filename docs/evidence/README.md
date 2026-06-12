# InvForge evidence logs

This directory holds **local validation evidence** for senior QA passes and final
packaging. Timestamped machine logs are **not** committed by default (see
`.gitignore`).

## PR-13 — Final packaging

| Artifact | Purpose |
|----------|---------|
| `PR13_FINAL_PACKAGING_REPORT.md` | PR-13 branch/SHA, validation table, screenshot status, readiness verdict |
| `../assets/screenshots/` | Portfolio screenshots (committed PNGs) |
| `../assets/screenshots/SCREENSHOT_MANIFEST.md` | Per-screenshot PASS/FAIL/MANUAL status from capture script |
| `../screenshots.md` | Screenshot list, commands, manual fallback steps |

## PR-12.6 — Senior QA + usable demo

| Artifact | Purpose |
|----------|---------|
| `PR12_6_SENIOR_QA_USABLE_DEMO.md` | Human-readable senior QA report (branch, SHA, PASS/FAIL table, blockers) |
| `pr12-6-local/<timestamp>/` | Timestamped collector output (`SUMMARY.md`, `tools.txt`, `logs/`) |

Collect fresh evidence:

```bash
# Safe default — static/offline checks only
bash scripts/collect_pr12_6_evidence.sh --static

# Opt-in heavy sections (run one at a time on 8 GB machines)
bash scripts/collect_pr12_6_evidence.sh --docker
bash scripts/collect_pr12_6_evidence.sh --k8s
bash scripts/collect_pr12_6_evidence.sh --observability
bash scripts/collect_pr12_6_evidence.sh --observability-combined   # AI + obs + alert-test
bash scripts/collect_pr12_6_evidence.sh --lineage
```

## Screenshot list (PR-13)

| File | Status | Notes |
|------|--------|-------|
| `dashboard-overview.png` | See manifest | Streamlit overview after `make demo-local` |
| `dashboard-decision-intelligence.png` | See manifest | Decision intel panel |
| `dashboard-mlops.png` | See manifest | MLOps status panel |
| `api-health.png` | See manifest | `/health` JSON |
| `api-docs.png` | See manifest | FastAPI OpenAPI UI |
| `grafana-observability.png` | See manifest | Local Grafana (Docker) |
| `marquez-lineage.png` | MANUAL REQUIRED | kind lineage profile |
| `github-actions-green.png` | MANUAL REQUIRED AFTER PUSH | Export from GitHub Actions UI |
| `terminal-demo-local-pass.png` | MANUAL OPTIONAL | Terminal or `demo-local-pass.log` |

## What is proven vs what is not proven

| Claim | Proven? | Evidence |
|-------|---------|----------|
| Local pipeline + dashboard usable | **Yes** | PR-12.6 + PR-13 screenshots |
| API health/metrics/docs work locally | **Yes** | PR-12.6 + api-health/api-docs screenshots |
| Deploy profiles validate offline | **Yes** | `make deploy-validate`, PR-12.6 |
| kind observability alert loop | **Yes** | PR-12.6 combined obs test |
| Marquez retraining lineage | **Yes** (local kind) | PR-12.6 lineage smoke; screenshot manual |
| Live Cloud Run / ECS / Azure deploy | **No** | Templates only — see `docs/cloud/` |
| Production ROI / customer savings | **No** | Synthetic data only |
| GitHub Actions green for PR-13 | **Verify after push** | Not claimed until CI runs on PR branch |

Prior audit: `docs/audits/pr12-full-qa-audit.md` (PR-12 static pass).

## GitHub Actions status reminder

- PR-12.6 was green on merge to `main` (CI, Deploy Validation, Security).
- **PR-13 checks must be verified after push** — do not claim green until the PR UI shows passing workflows.
