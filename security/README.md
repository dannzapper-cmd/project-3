# InvForge Defensive Security (PR-08)

PR-08 adds a **defensive operational security layer** to InvForge, the external AI Operations sidecar over InvenTree. It does not modify InvenTree core. The layer ingests existing synthetic inventory movement CSVs (PR-01), produces explainable risk indicators and anomaly scores, and writes portfolio-safe artifacts under `artifacts/security/`.

## Components

| Module | Role |
|--------|------|
| `security/audit.py` | `AuditLogger` — append-only JSONL audit events with a fixed schema |
| `security/risk_scorer.py` | `RiskScorer` — weighted, explainable rules for suspicious movements |
| `security/anomaly.py` | `AnomalyDetector` — deterministic `IsolationForest` over movement features |
| `security/pipeline.py` | Orchestrates audit + scoring + anomaly detection |
| `security/constants.py` | Named weights, thresholds, and model parameters |
| `security/smoke_check.py` | Fast artifact validation (no pytest) |
| `security/checks.py` | Runs Bandit, pip-audit, and detect-secrets |

## Input data

The pipeline reads **only** existing PR-01 outputs:

- `data/synthetic/output/stock_movements.csv`
- (loaded for context; scoring/anomaly focus on movements)

If `stock_movements.csv` is missing, `make security-audit` runs `make generate-data` automatically, or exits with a clear error.

## Generated artifacts (runtime, not committed)

| File | Description |
|------|-------------|
| `artifacts/security/audit_log.jsonl` | One JSON object per line: timestamp, event_type, severity, actor, part_id, movement_id, description, metadata |
| `artifacts/security/risk_score_summary.json` | Array of per-movement risk scores with `factors` and `rule_triggered` |
| `artifacts/security/anomaly_results.csv` | `movement_id`, `part_id`, `date`, `quantity`, `anomaly_score`, `is_anomaly`, `features_used` |
| `artifacts/security/security_summary.json` | Aggregate posture (`CLEAN` / `ELEVATED` / `HIGH_RISK`), counts, and model metadata |

Artifacts must not contain API keys, tokens, passwords, or environment variable values.

## Makefile targets

```bash
make security-audit    # generate all four artifacts (runs generate-data if needed)
make security-smoke    # validate artifacts exist and match expected shape
make security-check    # Bandit + pip-audit + detect-secrets (all must pass)
make trivy-scan        # local Trivy FS scan (requires trivy CLI)
make sbom              # CycloneDX SBOM via syft (requires syft CLI)
```

### Local tooling

**Trivy** (filesystem vulnerability scan):

```bash
# Debian/Ubuntu example
sudo apt-get install wget apt-transport-https gnupg lsb-release
wget -qO - https://aquasecurity.github.io/trivy-repo/deb/public.key | sudo apt-key add -
echo "deb https://aquasecurity.github.io/trivy-repo/deb $(lsb_release -sc) main" | sudo tee /etc/apt/sources.list.d/trivy.list
sudo apt-get update && sudo apt-get install trivy
```

**Syft** (SBOM):

```bash
curl -sSfL https://raw.githubusercontent.com/anchore/syft/main/install.sh | sh -s -- -b /usr/local/bin
```

In CI, Trivy and SBOM run in `.github/workflows/security.yml`. The SBOM is uploaded as a workflow artifact on pushes to `main` (not on pull requests).

## Risk scoring rules

Weights are defined in `security/constants.py`:

| Rule | Weight | Trigger |
|------|--------|---------|
| Quantity spike | 0.35 | `quantity > 3×` part std |
| Extreme negative adjustment | 0.25 | `adjustment` with `quantity < -10` |
| Repeated movements | 0.20 | ≥3 movements on same part within 3 days |
| Unknown reference | 0.10 | Missing or non-matching reference pattern |
| Data quality | 0.10 | Unexpected `movement_type` |

Final score is capped at `1.0`. Risk levels: LOW (≤0.3), MEDIUM (≤0.6), HIGH (≤0.85), CRITICAL (>0.85).

## Anomaly detection

- Model: `IsolationForest` with `contamination=0.05`, `random_state=42`, `n_estimators=100`
- Features: `quantity`, `movement_type_encoded`, `day_of_week`, `is_weekend`, `quantity_zscore_per_part`
- Skipped when fewer than 20 samples (logged as `SYSTEM_CHECK` WARNING)

Signals are **marked for human review**, not treated as confirmed malicious activity.

### Operational hours

Events outside the default window (08:00–20:00 UTC) are logged at INFO for review. Configure via `SECURITY_OPS_HOURS_START` / `SECURITY_OPS_HOURS_END` (future wiring; constants `OPS_HOURS_START` / `OPS_HOURS_END` in code).

## Scope: Defensive Only

PR-08 implements defensive operational security only. No offensive techniques, no exploit simulation, no credential testing. Red-team simulation and data poisoning detection are documented as future Senior Edition scope (PR-11).

## Future / Senior Edition

- `GET /api/v1/security/status` and audit tail endpoints (PR-12/PR-13)
- Streamlit security posture panel (read-only via API)
- Model signing / Cosign / Sigstore
- Rate limiting, RBAC, and full SIEM integration
- Scheduled retraining and automated response playbooks

## Known limitations

- Risk rules are heuristic, not ML-trained classifiers.
- Anomaly detection requires ≥20 movements globally; sparse catalogs may skip the model.
- `pip-audit` and Trivy report upstream dependency/CVE noise; triage may be needed.
- After-hours detection uses movement `date` only (no time-of-day in PR-01 CSVs unless extended).

## Known Static Analysis Findings

None at PR-08 introduction. If Bandit reports new MEDIUM findings, document justification here.

## CI

See `.github/workflows/security.yml`:

- **security-checks**: Bandit, pip-audit, detect-secrets, pipeline, smoke, pytest
- **trivy-scan**: CRITICAL fails the job; HIGH is reported only
- **sbom**: CycloneDX SBOM artifact on `main` pushes
