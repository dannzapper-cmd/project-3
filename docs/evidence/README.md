# InvForge evidence logs

This directory holds **local validation evidence** for senior QA passes. Logs are
generated on a developer machine and are **not** committed by default (see
`.gitignore`).

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

Prior audit: `docs/audits/pr12-full-qa-audit.md` (PR-12 static pass; live Docker/kind
was MANUAL REQUIRED in Cursor Cloud).
