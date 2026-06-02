#!/usr/bin/env python3
"""Generate PR-04 decision intelligence artifacts from PR-03 forecasts."""

from __future__ import annotations

import argparse
import json
import logging
import os
import warnings
from pathlib import Path
from typing import Any

import mlflow
import numpy as np
import pandas as pd

from ml.data import load_demand_training_table, subset_items_days
from ml.decision import (
    FORBIDDEN_DECISION_FEATURES,
    calculate_eoq,
    calculate_reorder_point,
    calculate_safety_stock,
    enforce_prediction_interval_monotonicity,
    nearest_quantile_alpha,
    newsvendor_quantile,
    pinball_loss,
    risk_level,
    service_level_to_z_score,
    simulated_inventory_cost,
    stockout_risk_normal,
    validate_forecast_feature_columns,
)
from ml.features import (
    TARGET_COLUMN,
    build_features,
    drop_rows_with_incomplete_features,
)
from ml.models.lightgbm_model import (
    predict_quantile_models,
    train_quantile_models,
)
from ml.models.statsforecast_model import fit_predict_statsforecast_intervals
from ml.split import temporal_train_test_split
from ml.train import load_config

logger = logging.getLogger(__name__)

DEFAULT_DECISION_CONFIG: dict[str, Any] = {
    "artifact_dir": "artifacts/decision",
    "service_level": 0.95,
    "quantile_alphas": [0.1, 0.5, 0.9],
    "forecast_excluded_features": ["lead_time_days"],
    "eoq": {
        "order_cost": 50.0,
        "holding_cost_rate": 0.20,
    },
    "cost": {
        "understock_cost_multiplier": 1.0,
        "naive_policy": "lag_7",
    },
    "risk": {
        "low_threshold": 0.20,
        "high_threshold": 0.50,
    },
    "statsforecast_interval_reference": {
        "enabled": True,
        "level": 80,
    },
    "mlflow": {
        "experiment_name": "decision_intelligence",
        "enabled": True,
    },
}


def _deep_merge(defaults: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    merged = defaults.copy()
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _json_default(value: Any) -> Any:
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, Path):
        return str(value)
    if pd.isna(value):
        return None
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _quantile_column(alpha: float) -> str:
    return f"q{int(round(float(alpha) * 100)):02d}"


def _load_parts_metadata(synthetic_dir: Path, parts_file: str) -> pd.DataFrame:
    path = synthetic_dir / parts_file
    if not path.exists():
        raise FileNotFoundError(
            f"Parts metadata not found at {path}. Run `make generate-data` first."
        )

    parts = pd.read_csv(path)
    defaults: dict[str, Any] = {
        "part_id": "",
        "demand_pattern": "unknown",
        "lead_time_days": 1.0,
        "current_stock": 0.0,
        "unit_cost": np.nan,
    }
    for col, default in defaults.items():
        if col not in parts.columns:
            warnings.warn(
                f"Missing parts metadata column {col}; using default {default}",
                stacklevel=2,
            )
            parts[col] = default

    keep_cols = [
        "part_id",
        "demand_pattern",
        "lead_time_days",
        "current_stock",
        "unit_cost",
    ]
    metadata = parts[keep_cols].drop_duplicates(subset=["part_id"]).copy()
    metadata["part_id"] = metadata["part_id"].astype(str)
    for col in ("lead_time_days", "current_stock", "unit_cost"):
        metadata[col] = pd.to_numeric(metadata[col], errors="coerce")
    return metadata


def _build_backtest_frame(
    test_df: pd.DataFrame,
    quantile_predictions: pd.DataFrame,
    parts_metadata: pd.DataFrame,
    *,
    available_alphas: list[float],
    holding_cost_rate: float,
    understock_cost_multiplier: float,
) -> pd.DataFrame:
    intervals = enforce_prediction_interval_monotonicity(quantile_predictions)

    backtest = test_df[
        ["part_id", "date", TARGET_COLUMN, "lag_7", "demand_pattern"]
    ].copy()
    backtest["part_id"] = backtest["part_id"].astype(str)
    backtest["date"] = pd.to_datetime(backtest["date"])
    backtest = pd.concat(
        [backtest.reset_index(drop=True), intervals.reset_index(drop=True)],
        axis=1,
    )
    quantile_predictions = quantile_predictions.reset_index(drop=True)
    for alpha in available_alphas:
        col = _quantile_column(alpha)
        backtest[col] = quantile_predictions[col].clip(lower=0.0)

    backtest = backtest.merge(parts_metadata, on="part_id", how="left")
    backtest["unit_cost"] = pd.to_numeric(backtest["unit_cost"], errors="coerce")
    backtest["unit_cost_nonnegative"] = (
        backtest["unit_cost"].clip(lower=0.0).fillna(0.0)
    )
    backtest["understock_cost_per_unit"] = (
        backtest["unit_cost_nonnegative"] * understock_cost_multiplier
    )
    backtest["overstock_cost_per_unit"] = (
        backtest["unit_cost_nonnegative"] * holding_cost_rate / 365.0
    )

    q_values = []
    selected_alphas = []
    selected_forecasts = []
    for row in backtest.itertuples(index=False):
        q_value = newsvendor_quantile(
            float(row.understock_cost_per_unit),
            float(row.overstock_cost_per_unit),
        )
        selected_alpha = nearest_quantile_alpha(q_value, available_alphas)
        q_values.append(q_value)
        selected_alphas.append(selected_alpha)
        selected_forecasts.append(getattr(row, _quantile_column(selected_alpha)))

    backtest["newsvendor_quantile"] = q_values
    backtest["selected_quantile_alpha"] = selected_alphas
    backtest["selected_quantile_forecast"] = selected_forecasts
    backtest["naive_policy_forecast"] = backtest["lag_7"].clip(lower=0.0)
    return backtest


def _simulate_cost_metrics(backtest: pd.DataFrame) -> dict[str, float | bool]:
    actual = backtest[TARGET_COLUMN]
    optimized = backtest["selected_quantile_forecast"]
    naive = backtest["naive_policy_forecast"]
    understock = backtest["understock_cost_per_unit"]
    overstock = backtest["overstock_cost_per_unit"]

    optimized_total = simulated_inventory_cost(
        actual,
        optimized,
        understock,
        overstock,
    )
    naive_total = simulated_inventory_cost(actual, naive, understock, overstock)
    cost_reduction_pct = (
        ((naive_total - optimized_total) / naive_total) * 100.0
        if naive_total > 0
        else 0.0
    )

    return {
        "naive_total_cost": naive_total,
        "optimized_total_cost": optimized_total,
        "cost_reduction_pct": float(cost_reduction_pct),
        "optimized_cost_lt_naive": bool(optimized_total < naive_total),
        "selected_pinball_loss": pinball_loss(
            actual,
            optimized,
            backtest["newsvendor_quantile"],
        ),
    }


def _build_recommendations(
    train_df: pd.DataFrame,
    backtest: pd.DataFrame,
    parts_metadata: pd.DataFrame,
    *,
    service_level: float,
    order_cost: float,
    holding_cost_rate: float,
    risk_low_threshold: float,
    risk_high_threshold: float,
) -> pd.DataFrame:
    z_score = service_level_to_z_score(service_level)

    demand_std = (
        train_df.assign(part_id=train_df["part_id"].astype(str))
        .groupby("part_id", observed=True)[TARGET_COLUMN]
        .std(ddof=0)
        .fillna(0.0)
        .rename("demand_std_daily")
        .reset_index()
    )

    forecast_summary = (
        backtest.groupby("part_id", observed=True)
        .agg(
            forecast_mean_daily=("prediction", "mean"),
            prediction_lower=("prediction_lower", "mean"),
            prediction=("prediction", "mean"),
            prediction_upper=("prediction_upper", "mean"),
            selected_quantile_forecast_daily=("selected_quantile_forecast", "mean"),
            newsvendor_quantile=("newsvendor_quantile", "mean"),
            selected_quantile_alpha=("selected_quantile_alpha", "median"),
        )
        .reset_index()
    )

    recommendations = (
        forecast_summary.merge(demand_std, on="part_id", how="left")
        .merge(parts_metadata, on="part_id", how="left")
        .sort_values("part_id")
        .reset_index(drop=True)
    )
    recommendations["demand_std_daily"] = recommendations[
        "demand_std_daily"
    ].fillna(0.0)
    recommendations["lead_time_days"] = pd.to_numeric(
        recommendations["lead_time_days"],
        errors="coerce",
    ).fillna(1.0)
    recommendations["current_stock"] = pd.to_numeric(
        recommendations["current_stock"],
        errors="coerce",
    ).fillna(0.0)
    recommendations["unit_cost"] = pd.to_numeric(
        recommendations["unit_cost"],
        errors="coerce",
    )

    recommendations["service_level"] = service_level
    recommendations["z_score"] = z_score
    recommendations["order_cost"] = order_cost
    recommendations["annual_holding_cost_per_unit"] = (
        recommendations["unit_cost"] * holding_cost_rate
    )
    recommendations["annual_demand"] = recommendations["forecast_mean_daily"] * 365.0
    recommendations["demand_during_lead_time"] = (
        recommendations["forecast_mean_daily"] * recommendations["lead_time_days"]
    )

    row_warnings: list[str] = []
    safety_stock_values: list[float] = []
    reorder_points: list[float] = []
    eoq_values: list[float] = []
    stockout_risks: list[float] = []
    risk_levels: list[str] = []

    for row in recommendations.itertuples(index=False):
        messages: list[str] = []
        if row.lead_time_days <= 0:
            messages.append("non_positive_lead_time")
        if row.current_stock < 0:
            messages.append("negative_current_stock")
        if not np.isfinite(row.unit_cost) or row.unit_cost <= 0:
            messages.append("non_positive_unit_cost")

        safety_stock = calculate_safety_stock(
            z_score,
            float(row.demand_std_daily),
            float(row.lead_time_days),
        )
        reorder_point = calculate_reorder_point(
            float(row.demand_during_lead_time),
            safety_stock,
        )
        eoq = calculate_eoq(
            float(row.annual_demand),
            float(order_cost),
            float(row.annual_holding_cost_per_unit),
        )
        stockout_risk = stockout_risk_normal(
            float(row.forecast_mean_daily),
            float(row.demand_std_daily),
            float(row.lead_time_days),
            float(row.current_stock),
        )

        safety_stock_values.append(safety_stock)
        reorder_points.append(reorder_point)
        eoq_values.append(eoq)
        stockout_risks.append(stockout_risk)
        risk_levels.append(
            risk_level(
                stockout_risk,
                low_threshold=risk_low_threshold,
                high_threshold=risk_high_threshold,
            )
        )
        row_warnings.append(";".join(messages))

    recommendations["safety_stock"] = safety_stock_values
    recommendations["reorder_point"] = reorder_points
    recommendations["eoq"] = eoq_values
    recommendations["stockout_risk"] = stockout_risks
    recommendations["risk_level"] = risk_levels
    recommendations["warnings"] = row_warnings

    ordered_cols = [
        "part_id",
        "demand_pattern",
        "service_level",
        "z_score",
        "lead_time_days",
        "current_stock",
        "unit_cost",
        "forecast_mean_daily",
        "prediction_lower",
        "prediction",
        "prediction_upper",
        "demand_std_daily",
        "demand_during_lead_time",
        "safety_stock",
        "reorder_point",
        "annual_demand",
        "order_cost",
        "annual_holding_cost_per_unit",
        "eoq",
        "stockout_risk",
        "risk_level",
        "newsvendor_quantile",
        "selected_quantile_alpha",
        "selected_quantile_forecast_daily",
        "warnings",
    ]
    return recommendations[ordered_cols]


def _statsforecast_interval_reference(
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    parts_patterns: dict[str, str],
    config: dict[str, Any],
) -> dict[str, Any]:
    if not config.get("enabled", True):
        return {"enabled": False, "skipped_reason": "disabled"}

    level = int(config.get("level", 80))
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            interval_df, model_usage = fit_predict_statsforecast_intervals(
                train_df,
                test_df,
                parts_patterns,
                level=level,
            )
        valid = interval_df[["yhat_lower", "yhat_upper"]].notna().all(axis=1)
        if not valid.any():
            return {
                "enabled": True,
                "level": level,
                "skipped_reason": "no_native_interval_columns_returned",
                "model_usage": model_usage,
            }
        covered = (
            (interval_df.loc[valid, "y"] >= interval_df.loc[valid, "yhat_lower"])
            & (interval_df.loc[valid, "y"] <= interval_df.loc[valid, "yhat_upper"])
        )
        width = (
            interval_df.loc[valid, "yhat_upper"]
            - interval_df.loc[valid, "yhat_lower"]
        )
        return {
            "enabled": True,
            "level": level,
            "coverage": float(covered.mean()),
            "average_width": float(width.mean()),
            "rows": int(valid.sum()),
            "model_usage": model_usage,
        }
    except Exception as exc:
        logger.warning("StatsForecast interval reference skipped: %s", exc)
        return {
            "enabled": True,
            "level": level,
            "skipped_reason": f"{type(exc).__name__}: {exc}",
        }


def _write_artifacts(
    recommendations: pd.DataFrame,
    summary: dict[str, Any],
    artifact_dir: Path,
) -> tuple[Path, Path]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    recommendations_path = artifact_dir / "decision_recommendations.csv"
    summary_path = artifact_dir / "decision_summary.json"
    recommendations.to_csv(recommendations_path, index=False)
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True, default=_json_default),
        encoding="utf-8",
    )
    return recommendations_path, summary_path


def run_decision_intelligence(
    config: dict[str, Any],
    *,
    max_items: int | None = None,
    max_days: int | None = None,
) -> dict[str, Any]:
    """Execute PR-04 decision intelligence pipeline and return artifact summary."""

    decision_cfg = _deep_merge(DEFAULT_DECISION_CONFIG, config.get("decision", {}))
    data_cfg = config["data"]
    synthetic_dir = Path(data_cfg["synthetic_dir"])

    raw = load_demand_training_table(
        synthetic_dir,
        demand_file=data_cfg.get("demand_history_file", "demand_history.csv"),
        parts_file=data_cfg.get("parts_file", "parts.csv"),
    )
    if max_items is not None and max_days is not None:
        raw = subset_items_days(raw, max_items=max_items, max_days=max_days)

    featured = build_features(raw)
    complete = drop_rows_with_incomplete_features(featured)
    train_fraction = config.get("split", {}).get("train_fraction", 0.75)
    train_df, test_df = temporal_train_test_split(
        complete,
        train_fraction=train_fraction,
    )

    alphas = [float(alpha) for alpha in decision_cfg["quantile_alphas"]]
    required_alphas = {0.1, 0.5, 0.9}
    if not required_alphas.issubset(set(alphas)):
        raise ValueError("decision.quantile_alphas must include 0.1, 0.5, and 0.9")

    excluded_features = set(decision_cfg.get("forecast_excluded_features", []))
    forbidden_features = FORBIDDEN_DECISION_FEATURES.union(excluded_features)
    parts_metadata = _load_parts_metadata(
        synthetic_dir,
        data_cfg.get("parts_file", "parts.csv"),
    )

    mlflow_cfg = config.get("mlflow", {})
    decision_mlflow_cfg = decision_cfg.get("mlflow", {})
    tracking_uri = mlflow_cfg.get("tracking_uri", "mlruns")
    experiment_name = decision_mlflow_cfg.get(
        "experiment_name",
        "decision_intelligence",
    )
    mlflow_enabled = bool(decision_mlflow_cfg.get("enabled", True))
    os.environ.setdefault("MLFLOW_TRACKING_URI", tracking_uri)
    os.environ.setdefault("MLFLOW_ALLOW_FILE_STORE", "true")
    if mlflow_enabled:
        mlflow.set_tracking_uri(tracking_uri)
        mlflow.set_experiment(experiment_name)

    parts_patterns = (
        raw.drop_duplicates("part_id").set_index("part_id")["demand_pattern"].to_dict()
    )
    service_level = float(decision_cfg["service_level"])
    z_score = service_level_to_z_score(service_level)
    order_cost = float(decision_cfg["eoq"]["order_cost"])
    holding_cost_rate = float(decision_cfg["eoq"]["holding_cost_rate"])
    understock_multiplier = float(
        decision_cfg["cost"]["understock_cost_multiplier"]
    )
    risk_low_threshold = float(decision_cfg["risk"]["low_threshold"])
    risk_high_threshold = float(decision_cfg["risk"]["high_threshold"])

    run_context = (
        mlflow.start_run(run_name="decision_intelligence") if mlflow_enabled else None
    )

    try:
        if mlflow_enabled:
            mlflow.log_params(
                {
                    "train_fraction": train_fraction,
                    "train_rows": len(train_df),
                    "test_rows": len(test_df),
                    "num_items": int(raw["part_id"].nunique()),
                    "service_level": service_level,
                    "z_score": z_score,
                    "quantile_alphas": json.dumps(alphas),
                    "forecast_excluded_features": json.dumps(sorted(excluded_features)),
                    "eoq_order_cost_usd": order_cost,
                    "eoq_holding_cost_rate": holding_cost_rate,
                    "eoq_annual_holding_cost_per_unit": (
                        f"unit_cost * {holding_cost_rate}"
                    ),
                    "understock_cost_multiplier": understock_multiplier,
                    "overstock_cost_per_unit": (
                        f"unit_cost * {holding_cost_rate} / 365"
                    ),
                    "risk_low_threshold": risk_low_threshold,
                    "risk_high_threshold": risk_high_threshold,
                    "cost_baseline_policy": decision_cfg["cost"]["naive_policy"],
                    "synthetic_simulated_backtest": "true",
                }
            )

        quantile_models, quantile_features = train_quantile_models(
            train_df,
            config.get("lightgbm", {}),
            alphas=alphas,
            excluded_features=excluded_features,
        )
        validate_forecast_feature_columns(
            quantile_features,
            forbidden=forbidden_features,
        )

        if mlflow_enabled:
            for alpha, model in sorted(quantile_models.items()):
                mlflow.lightgbm.log_model(
                    model,
                    artifact_path=f"lightgbm_quantile_p{int(round(alpha * 100)):02d}",
                )

        quantile_predictions = predict_quantile_models(
            quantile_models,
            test_df,
            quantile_features,
        )
        backtest = _build_backtest_frame(
            test_df,
            quantile_predictions,
            parts_metadata,
            available_alphas=alphas,
            holding_cost_rate=holding_cost_rate,
            understock_cost_multiplier=understock_multiplier,
        )
        cost_metrics = _simulate_cost_metrics(backtest)

        recommendations = _build_recommendations(
            train_df,
            backtest,
            parts_metadata,
            service_level=service_level,
            order_cost=order_cost,
            holding_cost_rate=holding_cost_rate,
            risk_low_threshold=risk_low_threshold,
            risk_high_threshold=risk_high_threshold,
        )

        sf_reference = _statsforecast_interval_reference(
            train_df,
            test_df,
            parts_patterns,
            decision_cfg["statsforecast_interval_reference"],
        )

        artifact_dir = Path(decision_cfg["artifact_dir"])
        summary: dict[str, Any] = {
            "scope": "PR-04 decision intelligence",
            "data_source": "synthetic",
            "seed": 42,
            "train_period": (
                f"{train_df['date'].min().date()} to {train_df['date'].max().date()}"
            ),
            "test_period": (
                f"{test_df['date'].min().date()} to {test_df['date'].max().date()}"
            ),
            "recommendation_rows": int(len(recommendations)),
            "backtest_rows": int(len(backtest)),
            "service_level": service_level,
            "z_score": z_score,
            "assumptions": {
                "lead_time": "fixed; demand variance only in safety stock",
                "order_cost_usd": order_cost,
                "annual_holding_cost_per_unit": f"unit_cost * {holding_cost_rate}",
                "understock_cost_per_unit": (
                    f"unit_cost * {understock_multiplier}"
                ),
                "overstock_cost_per_unit": (
                    f"unit_cost * {holding_cost_rate} / 365"
                ),
            },
            "cost_metrics": cost_metrics,
            "statsforecast_interval_reference": sf_reference,
            "limitations": [
                "synthetic data only",
                "simulated cost backtest only",
                "not a production savings claim",
            ],
        }
        if mlflow_enabled:
            active_run = mlflow.active_run()
            summary["run_id"] = active_run.info.run_id if active_run else None

        recommendations_path, summary_path = _write_artifacts(
            recommendations,
            summary,
            artifact_dir,
        )
        summary["artifacts"] = {
            "recommendations_csv": str(recommendations_path),
            "summary_json": str(summary_path),
        }
        summary_path.write_text(
            json.dumps(summary, indent=2, sort_keys=True, default=_json_default),
            encoding="utf-8",
        )

        if mlflow_enabled:
            mlflow.log_metrics(
                {
                    "naive_total_cost": float(cost_metrics["naive_total_cost"]),
                    "optimized_total_cost": float(cost_metrics["optimized_total_cost"]),
                    "cost_reduction_pct": float(cost_metrics["cost_reduction_pct"]),
                    "selected_pinball_loss": float(
                        cost_metrics["selected_pinball_loss"]
                    ),
                }
            )
            if "coverage" in sf_reference:
                mlflow.log_metric(
                    "statsforecast_interval_coverage",
                    float(sf_reference["coverage"]),
                )
                mlflow.log_metric(
                    "statsforecast_interval_average_width",
                    float(sf_reference["average_width"]),
                )
            mlflow.log_artifact(str(recommendations_path), artifact_path="decision")
            mlflow.log_artifact(str(summary_path), artifact_path="decision")

        return summary
    finally:
        if run_context is not None:
            mlflow.end_run()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate decision intelligence inventory recommendations."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("ml/config.yaml"),
        help="Path to YAML configuration",
    )
    parser.add_argument("--max-items", type=int, default=None, help="Limit items")
    parser.add_argument(
        "--max-days",
        type=int,
        default=None,
        help="Limit days per item",
    )
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = parse_args()
    config = load_config(args.config)
    summary = run_decision_intelligence(
        config,
        max_items=args.max_items,
        max_days=args.max_days,
    )

    artifacts = summary.get("artifacts", {})
    print("Decision intelligence complete.")
    print(f"  Recommendations: {artifacts.get('recommendations_csv')}")
    print(f"  Summary:         {artifacts.get('summary_json')}")
    print("  Cost metrics:", summary.get("cost_metrics"))


if __name__ == "__main__":
    main()
