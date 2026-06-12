# Model Card: Demand Forecast Baseline (PR-03)

## Overview

| Field | Value |
|-------|-------|
| **Model name** | `demand_forecast_baseline` |
| **Version** | PR-03 initial baseline |
| **MLflow experiment** | `demand_forecast_baseline` |
| **Last training run** | `6a79e86d044343b78e6bd305306f6586` (local) |

Global demand forecasting baselines for InvForge inventory operations: a single **LightGBM** model trained on all item-day rows, and **StatsForecast** statistical models selected by `demand_pattern`.

## Data Source

- **Source:** Synthetic inventory data (`data/synthetic/output/`), seed **42**, regenerated via `make generate-data`
- **Primary table:** `demand_history.csv` joined with part metadata from `parts.csv` (`category_id`, `supplier_id`, `lead_time_days`, `demand_pattern`)
- **No live InvenTree data** required for training
- **Items:** 120 parts (~36 intermittent, ~84 regular) over 365 days

## Train / Test Split

| Set | Date range |
|-----|------------|
| **Train** | 2024-01-29 → 2024-10-06 (first 75% of calendar dates after lag warmup) |
| **Test** | 2024-10-07 → 2024-12-30 (remaining 25%) |

Strict temporal split with assertion `train_max_date < test_min_date`. No random splits.

## Features

| Category | Features |
|----------|----------|
| Calendar | `day_of_week`, `month`, `week_of_year`, `is_weekend` |
| Lags | `lag_7`, `lag_14`, `lag_28` of `quantity_demand` |
| Rolling | `rolling_mean_7`, `rolling_mean_28`, `rolling_std_28` |
| Metadata | `part_id`, `category_id`, `supplier_id`, `lead_time_days`, `demand_pattern_intermittent` |

**Excluded (leakage / PR-04 scope):** `current_stock`, `reorder_point`, `safety_stock`, `unit_cost`

## Models

### Primary: LightGBM (global)

- One regressor on all series; `part_id`, `category_id`, `supplier_id` as categorical features
- Hyperparameters logged to MLflow (see `ml/config.yaml`)

### Statistical: StatsForecast (Nixtla)

| `demand_pattern` | Models |
|------------------|--------|
| `regular` | AutoETS, SeasonalNaive (forecast column: first configured model) |
| `intermittent` | CrostonClassic, CrostonSBA |

Classification uses the existing `demand_pattern` flag from synthetic data — not reclassified.

## Metrics (test set)

Values from local run `6a79e86d044343b78e6bd305306f6586`:

| Model | MAE | RMSE | MAPE (%) |
|-------|-----|------|----------|
| **LightGBM** | 2.113 | 3.116 | 26.37 |
| **StatsForecast** | 2.088 | 3.092 | 26.26 |

## Explainability

- **SHAP:** `TreeExplainer` on LightGBM; sample of 200 test rows (`random_state=42`)
- **Artifact:** `shap_beeswarm.png` logged to MLflow when computation succeeds
- On failure, training continues and skip reason is logged (see MLflow param `shap_skipped`)

## Leakage Controls

- Time-based train/test split only
- Lag and rolling features use `shift(1)` before rolling windows
- Stock and reorder fields excluded from features
- No target-derived features from the forecast horizon

## PR-04 Decision Intelligence Add-on

PR-04 adds a separate decision intelligence layer documented in
[`docs/decision-intelligence.md`](../decision-intelligence.md). The PR-03
baseline training behavior remains unchanged.

- LightGBM quantile regressors (`p10/p50/p90`) are trained via additive helper
  functions for decision intervals and cost-aware backtesting.
- Raw LightGBM p10/p90 and StatsForecast native conformal intervals are reported
  as references. The primary PR-04B interval metric is a split empirical
  residual calibration targeting 90% nominal coverage on the temporal holdout.
- Calibrated interval coverage and average width are reported overall and by
  `demand_pattern`. These are synthetic backtest diagnostics, not production
  guarantees.
- Default service level is `0.95`, with
  `z_score = scipy.stats.norm.ppf(service_level)`.
- Safety stock assumes fixed lead time and demand variance only.
- EOQ defaults are synthetic assumptions:
  - `order_cost = 50.0` USD
  - `annual_holding_cost_per_unit = unit_cost * 0.20`
- Stockout risk uses a Normal approximation during lead time.
- Cost simulation compares against multiple baselines (`lag_7`,
  `moving_average_7`, `moving_average_28`, and StatsForecast when available)
  and reports low / medium / high understock-to-overstock sensitivity scenarios.
- PR-04C adds deterministic policy grid search by `demand_pattern`, selecting
  service level, safety-stock multiplier, and order-quantity multiplier on a
  policy calibration window and reporting final metrics on a later policy
  evaluation window.
- Large synthetic cost reductions are flagged as sensitive to baseline and cost
  assumptions. They are not real-world savings claims.

## Known Limitations

- Synthetic data only; metrics do not reflect live InvenTree demand
- PR-04 prediction intervals and cost-aware metrics are synthetic decision
  artifacts, not production inventory policies
- Interval calibration uses the existing temporal holdout split into calibration
  and evaluation slices; a future independent backtest would be required for a
  stronger out-of-sample coverage claim
- Policy optimization uses a simplified daily policy-quantity approximation,
  not a production inventory simulator with purchase orders, receipts, or stock
  ledger dynamics
- Cost reduction depends on synthetic demand, policy assumptions, and configured
  understock/overstock scenarios
- StatsForecast uses the first configured model column per pattern batch (not ensembled)
- Short-history series may cause AutoETS failures on very small subsets (smoke tests use 90-day windows)
- MLflow 3.x requires `MLFLOW_ALLOW_FILE_STORE=true` for local `mlruns/` tracking

## Next Steps

- **PR-05 (done):** Local Evidently drift monitoring, MLflow registry metadata,
  champion/challenger comparison, and minimal BentoML packaging — see
  [`docs/mlops.md`](../mlops.md). Kubernetes/cluster serving is intentionally
  deferred.
- **PR-09 (done):** Local ZenML + Optuna retraining lifecycle with a
  conservative champion/challenger promotion gate and a safe, dry-run-by-default
  rollback path — see [`docs/retraining-pipeline.md`](../retraining-pipeline.md).
  The model lifecycle is now: PR-03 trains the baseline; PR-05 registers the
  `champion` alias; PR-09 retrains candidates and promotes them only when they
  beat the champion on the primary metric (`mae`) by the configured threshold,
  recording the previous champion as the rollback target. PR-03 baseline
  training behaviour is unchanged.
- **PR-10 / PR-11 Senior Edition (done locally):** container deploy profiles,
  local kind/Helm AI layer, and optional observability/lineage profiles. BentoML
  serving is templated but disabled until a real image is built.
- **Future benchmarks:** foundation model benchmarks (Chronos-2/TimesFM) and
  TFT/N-BEATS comparison.

## How to Reproduce

```bash
uv sync --group dev --group ml
make generate-data
make train-ml
```

View runs: `MLFLOW_ALLOW_FILE_STORE=true mlflow ui --backend-store-uri mlruns`
