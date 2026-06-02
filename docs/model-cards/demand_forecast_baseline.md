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

## Known Limitations

- Synthetic data only; metrics do not reflect live InvenTree demand
- No prediction intervals or quantile forecasts (PR-04)
- StatsForecast uses the first configured model column per pattern batch (not ensembled)
- Short-history series may cause AutoETS failures on very small subsets (smoke tests use 90-day windows)
- MLflow 3.x requires `MLFLOW_ALLOW_FILE_STORE=true` for local `mlruns/` tracking

## Next Steps

- **PR-04:** Safety stock, EOQ, reorder point, quantile loss, cost-aware forecasting, prediction intervals
- **PR-05:** Evidently drift monitoring, model registry, BentoML serving
- **PR-11 Senior Edition:** Foundation model benchmarks (Chronos-2/TimesFM) and TFT/N-BEATS comparison

## How to Reproduce

```bash
uv sync --group dev --group ml
make generate-data
make train-ml
```

View runs: `MLFLOW_ALLOW_FILE_STORE=true mlflow ui --backend-store-uri mlruns`
