# PR-03 Runbook — ML Demand Forecast Baseline

## Scope

Reproducible training and evaluation for demand forecasting using synthetic data only. No InvenTree core changes, no live inventory dependency.

## Setup

```bash
uv sync --group dev --group ml
make generate-data
```

## Train

```bash
make train-ml
# equivalent:
MLFLOW_TRACKING_URI=mlruns MLFLOW_ALLOW_FILE_STORE=true \
  uv run --group ml python -m ml.train --config ml/config.yaml
```

Smoke subset (10 items × 90 days):

```bash
uv run --group ml python -m ml.train --config ml/config.yaml --max-items 10 --max-days 90
```

## Validate

```bash
uv run ruff check .
uv run --group dev --group ml pytest
```

## MLflow

- Tracking URI: `mlruns/` (gitignored)
- Experiment: `demand_forecast_baseline`
- Requires `MLFLOW_ALLOW_FILE_STORE=true` (MLflow 3.x)

## Artifacts

- LightGBM model (`mlflow.lightgbm.log_model`)
- `feature_list.json`
- `shap_beeswarm.png` (when SHAP succeeds)
- Metrics: `lightgbm_*`, `statsforecast_*` (MAE, RMSE, MAPE)

## Model Card

See [docs/model-cards/demand_forecast_baseline.md](../model-cards/demand_forecast_baseline.md).
