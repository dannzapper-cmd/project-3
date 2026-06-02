#!/usr/bin/env python3
"""Train and evaluate PR-03 demand forecasting baselines."""

from __future__ import annotations

import argparse
import json
import logging
import os
import warnings
from pathlib import Path
from typing import Any

import mlflow
import pandas as pd
import yaml

from ml.data import load_demand_training_table, subset_items_days
from ml.features import (
    FEATURE_COLUMNS,
    TARGET_COLUMN,
    build_features,
    drop_rows_with_incomplete_features,
)
from ml.metrics import compute_metrics
from ml.models.lightgbm_model import predict_lightgbm, train_lightgbm
from ml.models.statsforecast_model import fit_predict_statsforecast
from ml.split import temporal_train_test_split

logger = logging.getLogger(__name__)


def load_config(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def log_shap_artifact(
    model: Any,
    test_df: pd.DataFrame,
    feature_names: list[str],
    *,
    sample_size: int,
    random_state: int,
) -> str | None:
    """Generate SHAP beeswarm plot; return skip reason if unsuccessful."""

    try:
        import matplotlib.pyplot as plt
        import shap
    except ImportError as exc:
        return f"SHAP/matplotlib import failed: {exc}"

    try:
        sample_n = min(sample_size, len(test_df))
        sample = test_df.sample(n=sample_n, random_state=random_state)
        X = sample[feature_names].copy()
        for col in ("part_id", "category_id", "supplier_id"):
            if col in X.columns:
                X[col] = X[col].astype("category")

        explainer = shap.TreeExplainer(model)
        shap_values = explainer.shap_values(X)

        plt.figure(figsize=(10, 6))
        shap.summary_plot(shap_values, X, show=False)
        plot_path = Path("shap_beeswarm.png")
        plt.tight_layout()
        plt.savefig(plot_path, dpi=120, bbox_inches="tight")
        plt.close()
        mlflow.log_artifact(str(plot_path))
        plot_path.unlink(missing_ok=True)
        return None
    except MemoryError:
        return "MemoryError during SHAP computation"
    except Exception as exc:
        return f"{type(exc).__name__}: {exc}"


def run_training(
    config: dict[str, Any],
    *,
    max_items: int | None = None,
    max_days: int | None = None,
) -> dict[str, Any]:
    """Execute full training pipeline and return summary metrics."""

    data_cfg = config["data"]
    synthetic_dir = Path(data_cfg["synthetic_dir"])

    raw = load_demand_training_table(synthetic_dir)
    if max_items is not None and max_days is not None:
        raw = subset_items_days(raw, max_items=max_items, max_days=max_days)

    featured = build_features(raw)
    complete = drop_rows_with_incomplete_features(featured)

    train_fraction = config.get("split", {}).get("train_fraction", 0.75)
    train_df, test_df = temporal_train_test_split(
        complete, train_fraction=train_fraction
    )

    parts_patterns = (
        raw.drop_duplicates("part_id").set_index("part_id")["demand_pattern"].to_dict()
    )

    mlflow_cfg = config.get("mlflow", {})
    tracking_uri = mlflow_cfg.get("tracking_uri", "mlruns")
    experiment_name = mlflow_cfg.get("experiment_name", "demand_forecast_baseline")

    os.environ.setdefault("MLFLOW_TRACKING_URI", tracking_uri)
    os.environ.setdefault("MLFLOW_ALLOW_FILE_STORE", "true")
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(experiment_name)

    shap_skip_reason: str | None = None
    results: dict[str, Any] = {}

    with mlflow.start_run(run_name="demand_forecast_baseline"):
        mlflow.log_params(
            {
                "train_fraction": train_fraction,
                "train_rows": len(train_df),
                "test_rows": len(test_df),
                "train_start": str(train_df["date"].min().date()),
                "train_end": str(train_df["date"].max().date()),
                "test_start": str(test_df["date"].min().date()),
                "test_end": str(test_df["date"].max().date()),
                "num_items": int(raw["part_id"].nunique()),
            }
        )
        mlflow.log_params(
            {f"lgbm_{k}": v for k, v in config.get("lightgbm", {}).items()}
        )

        feature_list = FEATURE_COLUMNS + ["part_id", "category_id", "supplier_id"]
        features_path = Path("feature_list.json")
        features_path.write_text(json.dumps(feature_list, indent=2), encoding="utf-8")
        mlflow.log_artifact(str(features_path))
        features_path.unlink(missing_ok=True)

        # LightGBM
        lgbm_model, lgbm_features = train_lightgbm(train_df, config.get("lightgbm", {}))
        lgbm_preds = predict_lightgbm(lgbm_model, test_df, lgbm_features)
        lgbm_metrics = compute_metrics(
            test_df[TARGET_COLUMN].to_numpy(), lgbm_preds
        )
        for name, value in lgbm_metrics.items():
            mlflow.log_metric(f"lightgbm_{name}", value)
        results["lightgbm"] = lgbm_metrics

        mlflow.lightgbm.log_model(lgbm_model, artifact_path="lightgbm_model")

        shap_cfg = config.get("shap", {})
        shap_skip_reason = log_shap_artifact(
            lgbm_model,
            test_df,
            lgbm_features,
            sample_size=shap_cfg.get("sample_size", 200),
            random_state=shap_cfg.get("random_state", 42),
        )
        if shap_skip_reason:
            logger.warning("SHAP skipped: %s", shap_skip_reason)
            mlflow.log_param("shap_skipped", shap_skip_reason)
        else:
            mlflow.log_param("shap_skipped", "false")

        # StatsForecast
        sf_cfg = config.get("statsforecast", {})
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            sf_preds, model_usage = fit_predict_statsforecast(
                train_df,
                test_df,
                parts_patterns,
                season_length=sf_cfg.get("season_length", 7),
                regular_model_names=sf_cfg.get("regular_models"),
                intermittent_model_names=sf_cfg.get("intermittent_models"),
            )
        sf_metrics = compute_metrics(
            test_df[TARGET_COLUMN].to_numpy(), sf_preds
        )
        for name, value in sf_metrics.items():
            mlflow.log_metric(f"statsforecast_{name}", value)
        results["statsforecast"] = sf_metrics
        mlflow.log_param("statsforecast_model_usage", json.dumps(model_usage))

        run = mlflow.active_run()
        results["run_id"] = run.info.run_id if run else None
        results["shap_skip_reason"] = shap_skip_reason
        results["train_period"] = (
            f"{train_df['date'].min().date()} to {train_df['date'].max().date()}"
        )
        results["test_period"] = (
            f"{test_df['date'].min().date()} to {test_df['date'].max().date()}"
        )
        results["feature_list"] = feature_list

    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train demand forecasting baselines.")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("ml/config.yaml"),
        help="Path to YAML configuration",
    )
    parser.add_argument(
        "--max-items",
        type=int,
        default=None,
        help="Limit items (smoke tests)",
    )
    parser.add_argument(
        "--max-days",
        type=int,
        default=None,
        help="Limit days per item (smoke tests)",
    )
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = parse_args()
    config = load_config(args.config)

    results = run_training(
        config,
        max_items=args.max_items,
        max_days=args.max_days,
    )

    print("Training complete.")
    print(f"  MLflow run_id: {results.get('run_id')}")
    print(f"  Train period:  {results.get('train_period')}")
    print(f"  Test period:   {results.get('test_period')}")
    print("  LightGBM metrics:", results.get("lightgbm"))
    print("  StatsForecast metrics:", results.get("statsforecast"))
    if results.get("shap_skip_reason"):
        print(f"  SHAP skipped: {results['shap_skip_reason']}")


if __name__ == "__main__":
    main()
