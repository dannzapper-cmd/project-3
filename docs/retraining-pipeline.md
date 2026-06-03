# Retraining Pipeline (PR-09)

PR-09 adds a **local, reproducible, auditable** retraining lifecycle for the
demand-forecasting model. It uses **ZenML** as a local DAG runner, **Optuna**
for bounded hyperparameter tuning, the existing **MLflow** registry/aliases
(from PR-05) for champion/challenger promotion, and a **safe rollback** path.

Everything runs on a laptop with no cloud, no Kubernetes, no scheduler, and no
paid services. It does **not** modify InvenTree core, PR-03 models, PR-04
decision intelligence, the PR-05 loop, or PR-07/PR-08 behaviour.

> **Honesty note.** All metrics below come from **synthetic data (seed 42)** and
> local evaluation only. No real-world performance or savings is claimed.

## What PR-09 adds

- A ZenML retraining pipeline (`mlops/retraining/`) with typed steps:
  load data → verify artifacts → load current champion → train (optionally
  Optuna-tuned) + evaluate candidate → compare candidate vs champion →
  promote-or-reject → write summary.
- A conservative, test-covered **promotion gate**.
- A **safe rollback** path: MLflow alias rollback when aliases exist, otherwise a
  rollback **manifest**. Rollback is **dry-run by default**.
- Stable, schema-versioned audit artifacts under `artifacts/retraining/`.
- Makefile targets: `retrain-smoke`, `retrain`, `retrain-tune`,
  `retraining-check`, `model-rollback`, `model-rollback-confirm`.

## Architecture of the retraining lifecycle

```
load_training_data → verify_artifacts → load_current_champion
        └────────────┬───────────────────────┘
                     ▼
        train_and_evaluate_candidate   (optional Optuna tuning inside)
                     ▼
        compare_candidate_to_champion  (promotion gate)
                     ▼
        promote_or_reject              (controlled MLflow alias mutation)
                     ▼
        write_retraining_summary       (artifacts + MLflow decision log)
```

The candidate is **always kept separate** from the champion until the promotion
gate passes. The champion model is re-evaluated on the **candidate's exact test
split** so the comparison is apples-to-apples.

### Why ZenML (not Airflow/Kubeflow) here

ZenML is used purely as a **local DAG runner** with typed steps and local
pipeline metadata (default SQLite stack). It gives us step boundaries, lineage,
and a clean contract without standing up a scheduler/cluster. Airflow, Prefect,
Dagster, and Kubeflow are scheduler/cluster-oriented and are out of scope for a
local, laptop-friendly PR. Remote scheduling and the ZenML cloud are
**intentionally deferred to PR-11**. PR-09 provides the *command contract*;
PR-11 can wrap it later.

## How to run

```bash
# Install the retraining dependency group (isolated; does not pollute dev/ml).
uv sync --group dev --group ml --group retraining
```

### Smoke retraining (fast, deterministic)

```bash
make retrain-smoke
```

- Generates synthetic data, then runs the pipeline on a small deterministic
  subset (10 items × 90 days), no Optuna, fixed seed 42.
- Self-bootstrapping: the **first** run promotes the candidate to establish a
  champion (`status: first_run_promoted`); subsequent runs perform a real
  champion/challenger comparison.
- Does **not** require BentoML, a running server, or a ZenML dashboard.

### Full local retraining

```bash
make retrain          # full dataset, conservative defaults, no tuning
```

### Optuna tuning (optional)

```bash
make retrain-tune     # smoke subset + bounded Optuna (n_trials capped at 3)
```

### Inspect / validate artifacts (no training)

```bash
make retraining-check
```

### Rollback (dry-run by default)

```bash
make model-rollback           # prints what it WOULD do; mutates nothing
make model-rollback-confirm   # actually moves the champion alias (explicit)
```

## Optuna tuning (bounded)

Tuning is **optional and off by default**. When enabled (`--tune` /
`RETRAINING_TUNE=true`):

- Objective = the **same primary metric** used by PR-03/PR-04/PR-05 (`mae`,
  lower is better) on a temporal validation slice carved from the **training**
  window (the test split is never used for tuning).
- `TPESampler(seed=...)` makes the search deterministic for a fixed seed.
- **Hard trial caps enforced in code**, not just config: smoke ≤ 3, full ≤ 20.
  A `timeout` is also passed to `study.optimize`, so tuning cannot run unbounded.
- Trials are written to `artifacts/retraining/optuna_trials.csv` with
  `trial_number, params, value, state, duration_seconds`.

## Champion/challenger comparison & promotion gate

The gate reuses the PR-05 `compare_models` math, so it respects
`metric_direction` (`lower_is_better` / `higher_is_better`) — never a hardcoded
comparison. The comparison block is stored explicitly:

| Field | Meaning |
|-------|---------|
| `candidate_metric` / `champion_metric` | Primary metric for each (re-evaluated on the same split). |
| `metric_direction` | `lower_is_better` or `higher_is_better`. |
| `absolute_delta` / `relative_delta_pct` | Candidate vs champion deltas. |
| `promotion_threshold` | Minimum relative improvement (%) to promote (default 5%). |
| `promoted` | Final boolean. |

A candidate is promoted **only if**:

1. data/artifact validation passes,
2. evaluation produced a **finite, numeric** primary metric, and
3. the candidate beats the champion by **at least** the threshold (in the
   correct direction) — **or** it is the first run and metrics are valid.

> "Pipeline completed without error" is **not** sufficient for promotion.

Status values: `promoted`, `first_run_promoted`, `rejected`, `failed`.

- **Rejected** (worse or too-close): champion is left **unchanged**, a
  `rejected_reason` is recorded, and the candidate run is still logged for
  auditability.
- **First run** (no champion): the first candidate is promoted to bootstrap the
  champion; `first_run: true` is recorded.

### Secondary / context-only metrics

`rmse`, `mape`, and any PR-04 cost-aware figures are recorded for context only
and **never** gate promotion. PR-04 cost deltas
(`estimated_*_cost_delta`) require a champion cost re-simulation and are
recorded as `null` with `cost_metric_available: false` when unavailable — they
are not faked.

### Statistical significance

A significance test (e.g. Diebold–Mariano) needs repeated forecast
errors/backtest windows. The current artifacts do not expose that shape cleanly,
so it is **deferred**, recorded honestly as:

> "Statistical significance testing requires repeated forecast errors/backtest
> windows and is deferred until richer backtesting artifacts are available."

## Rollback

Rollback restores the champion alias to the **previous** champion. It is always
**dry-run by default** and requires an explicit `--confirm`
(or `ROLLBACK_CONFIRM=true`) to mutate anything.

- **MLflow alias rollback** (`rollback_method: mlflow_alias`): available when
  aliases were configured (PR-05). The previous champion is recorded under the
  `previous_champion` alias *before* the champion alias is moved, so a target is
  always identifiable. **No model version is ever deleted.**
- **Manifest-only rollback** (`rollback_method: manifest_only`): when no usable
  alias exists, the `rollback_manifest.json` is the system of record;
  `make model-rollback` validates it and prints what a rollback would do.

Executing a rollback appends a `history` entry (timestamp + reason) to the
manifest. Nothing is deleted.

## Failure & degradation behaviour

If retraining fails:

- the current champion remains **unchanged**;
- `retraining_summary.json` records `status: failed` with a `failure_reason`;
- `rollback_manifest.json` still identifies the last known safe champion;
- the system is never left half-promoted.

## Artifacts generated

All under `artifacts/retraining/` (git-ignored, like other generated artifacts):

| File | Contents |
|------|----------|
| `retraining_summary.json` | Audit-stable run summary (schema below). |
| `rollback_manifest.json` | Champion before/after, rollback target + method, metrics. |
| `latest_candidate_metrics.json` | Candidate primary + secondary metrics. |
| `latest_comparison.json` | The explicit comparison block. |
| `optuna_trials.csv` | Per-trial params/values (only when tuning runs). |
| `error_analysis.json` | Per-item worst errors + intermittent/regular breakdown. |

### `retraining_summary.json` schema (`schema_version` 1.0)

Required fields are **always present**; uncomputed numeric fields are `null`
(never a fake `0.0`), e.g. on failed/first-run cases:

`schema_version, run_id, timestamp, git_commit, pipeline_mode, model_name,
primary_metric, metric_direction, candidate_metric, champion_metric,
absolute_delta, relative_delta_pct, promotion_threshold, status, promoted,
rejected_reason, failure_reason, first_run, rollback_target, data_reference,
config_reference, bentoml_artifact, warnings`

Plus context blocks: `secondary_metrics`, `cost_context`,
`statistical_significance`, `tuning`, `package_versions`, `champion_before`,
`champion_after`.

### `rollback_manifest.json` schema (`schema_version` 1.0)

`schema_version, timestamp, champion_before, champion_after, candidate_run_id,
rollback_target, rollback_method, metrics_before, metrics_after,
dry_run_available` (plus `previous_champion`, `promoted_model`, `history`,
`notes`).

## Reproducibility

- Smoke mode is **deterministic**: fixed seed (`RETRAINING_RANDOM_SEED=42`),
  fixed data subset, `TPESampler(seed=42)`, deterministic LightGBM
  `random_state`.
- Each run records the **config used** (`config_reference`), **data references**
  (`data_reference`), **package versions** (`package_versions`), and the
  **git commit** (`git_commit`) so a run can be audited later.
- No hidden notebook state: the pipeline is plain typed Python.

## How to inspect MLflow runs

Retraining runs go to the `demand_forecast_retraining` experiment; the
registered model is `demand_forecast` with the `champion` (and, after a second
promotion, `previous_champion`) alias.

```bash
MLFLOW_ALLOW_FILE_STORE=true uv run --group ml mlflow ui --backend-store-uri mlruns
```

The candidate run logs params, `candidate_<metric>` metrics, the model, the
Optuna trials artifact (when tuning), and — after the decision — the promotion
status, `champion_metric`, `relative_delta_pct`, promoted version, and the
summary/manifest artifacts.

## BentoML packaging (reused, optional)

PR-09 reuses the **PR-05** BentoML packaging path (`mlops/packaging.py`) only
**after a promotion**, and only when `retraining.bentoml.enabled: true`. It is
**off by default**, so `make retrain-smoke` never requires BentoML or a running
server. The serving contract is unchanged; no new serving framework is added.

## Configuration

Configured in [`mlops/config.yaml`](../mlops/config.yaml) under `retraining:`
(reusing the existing MLOps config module — no new env sprawl). Environment
overrides for cron/CI:

| Variable | Effect |
|----------|--------|
| `RETRAINING_MODE` | `smoke` or `full`. |
| `RETRAINING_OPTUNA_TRIALS` | Requested trials (still clamped to the hard cap). |
| `RETRAINING_PROMOTION_THRESHOLD` | Promotion threshold (%). |
| `RETRAINING_RANDOM_SEED` | Deterministic seed. |
| `RETRAINING_TUNE` | Enable Optuna tuning. |
| `MLFLOW_TRACKING_URI` | MLflow store (default local `mlruns`). |

## Scheduling readiness (command contract only)

PR-09 does **not** implement scheduling. It provides a stable command contract
that a scheduler can call later. Retraining must be triggered **manually** today.

**Local cron example** (conceptual — not installed by this PR):

```cron
# Weekly local retraining; logs to a file. Manual/opt-in only.
0 3 * * 0 cd /path/to/invforge && make retrain >> /var/log/invforge_retrain.log 2>&1
```

**GitHub Actions (manual `workflow_dispatch`) example** (conceptual):

```yaml
on:
  workflow_dispatch: {}
jobs:
  retrain:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv sync --group dev --group ml --group retraining
      - run: make retrain-smoke
```

**Kubernetes CronJob:** explicitly **deferred to PR-11**. PR-09 deliberately
does not ship any k8s manifest.

## Implemented in PR-09

- Local ZenML retraining pipeline (smoke + full), deterministic smoke mode.
- Optional, bounded, deterministic Optuna tuning.
- Conservative, test-covered champion/challenger promotion gate.
- Safe rollback (MLflow alias when available, otherwise manifest), dry-run by
  default.
- Stable, schema-versioned audit artifacts + MLflow decision logging.
- Cron-ready command contract (documented, not scheduled).

## Deferred to PR-11 (Senior Edition) / later

- Kubernetes CronJob, Helm, k3s/kind, cloud schedulers.
- Blue/green deployment, remote ZenML stack / ZenML cloud.
- Statistical significance testing (needs richer backtest windows).
- Candidate-vs-champion **cost** deltas (needs champion cost re-simulation).
- LGTM stack, OpenLineage/Marquez, model signing, Redis, feature flags,
  foundation-model benchmarks.

## Known limitations

- **Synthetic data only** (seed 42); not a real-world performance claim.
- Local **file-store** MLflow registry/aliases; ephemeral per machine, no
  central server/governance.
- ZenML runs on the **local** default stack only; no remote orchestration.
- Champion comparison is a single temporal holdout, not a multi-window backtest.
- Rollback restores aliases/manifest only; it is **not** a production deployment
  rollback.
