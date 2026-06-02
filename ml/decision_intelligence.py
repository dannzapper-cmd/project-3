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
    interval_coverage_metrics,
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
from ml.models.statsforecast_model import (
    fit_predict_statsforecast,
    fit_predict_statsforecast_intervals,
)
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
        "baseline_policies": [
            "lag_7",
            "moving_average_7",
            "moving_average_28",
            "statsforecast",
        ],
        "sensitivity_understock_to_overstock_ratios": {
            "low": 5.0,
            "medium": 20.0,
            "high": 100.0,
        },
        "large_reduction_warning_threshold_pct": 50.0,
    },
    "interval_calibration": {
        "enabled": True,
        "nominal_coverage_target": 0.90,
        "calibration_fraction": 0.50,
        "method": "split_empirical_abs_residual_by_demand_pattern",
        "min_group_rows": 100,
        "minimum_acceptable_coverage": 0.85,
        "minimum_evaluation_rows_for_guard": 1000,
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


def _higher_quantile(values: pd.Series, quantile: float) -> float:
    """Deterministic empirical quantile used for residual calibration."""

    clean = pd.to_numeric(values, errors="coerce").dropna()
    if clean.empty:
        return 0.0
    return float(np.quantile(clean.to_numpy(), quantile, method="higher"))


def _interval_evaluation_split(
    backtest: pd.DataFrame,
    *,
    calibration_fraction: float,
) -> tuple[pd.Series, pd.Series, dict[str, str]]:
    dates = sorted(pd.to_datetime(backtest["date"]).unique())
    if len(dates) < 2:
        raise ValueError("Need at least two holdout dates for interval calibration")

    split_index = int(len(dates) * calibration_fraction)
    split_index = min(max(split_index, 1), len(dates) - 1)
    calibration_end = dates[split_index - 1]
    evaluation_start = dates[split_index]

    date_values = pd.to_datetime(backtest["date"])
    calibration_mask = date_values <= calibration_end
    evaluation_mask = date_values >= evaluation_start
    periods = {
        "calibration_period": (
            f"{date_values[calibration_mask].min().date()} to "
            f"{date_values[calibration_mask].max().date()}"
        ),
        "evaluation_period": (
            f"{date_values[evaluation_mask].min().date()} to "
            f"{date_values[evaluation_mask].max().date()}"
        ),
    }
    return calibration_mask, evaluation_mask, periods


def _apply_calibrated_intervals(
    backtest: pd.DataFrame,
    config: dict[str, Any],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Apply split empirical residual intervals and return evaluation metrics."""

    if not config.get("enabled", True):
        metrics = interval_coverage_metrics(
            backtest,
            actual_col=TARGET_COLUMN,
            lower_col="prediction_lower",
            upper_col="prediction_upper",
            group_col="demand_pattern",
        )
        metrics.update(
            {
                "method": "lightgbm_quantile_raw",
                "enabled": False,
                "nominal_coverage_target": None,
            }
        )
        return backtest, metrics

    target = float(config.get("nominal_coverage_target", 0.90))
    if not 0.0 < target < 1.0:
        raise ValueError("interval_calibration.nominal_coverage_target must be 0-1")

    calibration_mask, evaluation_mask, periods = _interval_evaluation_split(
        backtest,
        calibration_fraction=float(config.get("calibration_fraction", 0.50)),
    )
    calibrated = backtest.copy()
    calibrated["calibration_abs_error"] = (
        calibrated[TARGET_COLUMN] - calibrated["prediction"]
    ).abs()

    calibration = calibrated.loc[calibration_mask]
    overall_width = _higher_quantile(calibration["calibration_abs_error"], target)
    min_group_rows = int(config.get("min_group_rows", 100))
    group_widths: dict[str, float] = {}
    for pattern, group_df in calibration.groupby("demand_pattern", observed=True):
        if len(group_df) >= min_group_rows:
            group_widths[str(pattern)] = _higher_quantile(
                group_df["calibration_abs_error"],
                target,
            )

    calibrated["calibration_width"] = (
        calibrated["demand_pattern"].astype(str).map(group_widths).fillna(overall_width)
    )
    calibrated["prediction_lower"] = (
        calibrated["prediction"] - calibrated["calibration_width"]
    ).clip(lower=0.0)
    calibrated["prediction_upper"] = (
        calibrated["prediction"] + calibrated["calibration_width"]
    )

    evaluation = calibrated.loc[evaluation_mask].copy()
    metrics = interval_coverage_metrics(
        evaluation,
        actual_col=TARGET_COLUMN,
        lower_col="prediction_lower",
        upper_col="prediction_upper",
        group_col="demand_pattern",
    )
    metrics.update(
        {
            "method": config.get(
                "method",
                "split_empirical_abs_residual_by_demand_pattern",
            ),
            "enabled": True,
            "nominal_coverage_target": target,
            "overall_calibration_width": overall_width,
            "calibration_width_by_demand_pattern": group_widths,
            "calibration_rows": int(calibration_mask.sum()),
            "evaluation_rows": int(evaluation_mask.sum()),
            **periods,
            "coverage_width_tradeoff_notes": (
                "Residual widths are estimated on the first temporal half of the "
                "holdout and evaluated on the later half. Wider intervals improve "
                "coverage but reduce sharpness; metrics remain synthetic."
            ),
        }
    )

    min_coverage = float(config.get("minimum_acceptable_coverage", 0.85))
    min_eval_rows = int(config.get("minimum_evaluation_rows_for_guard", 1000))
    if metrics["rows"] >= min_eval_rows and metrics["coverage"] < min_coverage:
        raise RuntimeError(
            "Calibrated interval coverage fell below the configured acceptable "
            f"floor: {metrics['coverage']:.3f} < {min_coverage:.3f}"
        )

    return calibrated, metrics


def _select_newsvendor_forecast(
    backtest: pd.DataFrame,
    *,
    understock: pd.Series,
    overstock: pd.Series,
    available_alphas: list[float],
) -> tuple[list[float], list[float], list[float]]:
    q_values: list[float] = []
    selected_alphas: list[float] = []
    selected_forecasts: list[float] = []

    for idx, row in backtest.iterrows():
        q_value = newsvendor_quantile(
            float(understock.loc[idx]),
            float(overstock.loc[idx]),
        )
        selected_alpha = nearest_quantile_alpha(q_value, available_alphas)
        q_values.append(q_value)
        selected_alphas.append(selected_alpha)
        selected_forecasts.append(float(row[_quantile_column(selected_alpha)]))

    return q_values, selected_alphas, selected_forecasts


def _build_backtest_frame(
    test_df: pd.DataFrame,
    quantile_predictions: pd.DataFrame,
    statsforecast_predictions: np.ndarray | None,
    parts_metadata: pd.DataFrame,
    *,
    available_alphas: list[float],
    holding_cost_rate: float,
    understock_cost_multiplier: float,
) -> pd.DataFrame:
    raw_intervals = enforce_prediction_interval_monotonicity(quantile_predictions)

    backtest = test_df[
        [
            "part_id",
            "date",
            TARGET_COLUMN,
            "lag_7",
            "rolling_mean_7",
            "rolling_mean_28",
            "demand_pattern",
        ]
    ].copy()
    backtest["part_id"] = backtest["part_id"].astype(str)
    backtest["date"] = pd.to_datetime(backtest["date"])
    raw_intervals = raw_intervals.rename(
        columns={
            "prediction_lower": "raw_prediction_lower",
            "prediction_upper": "raw_prediction_upper",
        }
    )
    backtest = pd.concat(
        [backtest.reset_index(drop=True), raw_intervals.reset_index(drop=True)],
        axis=1,
    )
    backtest["prediction_lower"] = backtest["raw_prediction_lower"]
    backtest["prediction_upper"] = backtest["raw_prediction_upper"]
    quantile_predictions = quantile_predictions.reset_index(drop=True)
    for alpha in available_alphas:
        col = _quantile_column(alpha)
        backtest[col] = quantile_predictions[col].clip(lower=0.0)

    metadata_for_backtest = parts_metadata.drop(
        columns=["demand_pattern"],
        errors="ignore",
    )
    backtest = backtest.merge(metadata_for_backtest, on="part_id", how="left")
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

    q_values, selected_alphas, selected_forecasts = _select_newsvendor_forecast(
        backtest,
        understock=backtest["understock_cost_per_unit"],
        overstock=backtest["overstock_cost_per_unit"],
        available_alphas=available_alphas,
    )

    backtest["newsvendor_quantile"] = q_values
    backtest["selected_quantile_alpha"] = selected_alphas
    backtest["selected_quantile_forecast"] = selected_forecasts
    backtest["lag_7_policy_forecast"] = backtest["lag_7"].clip(lower=0.0)
    backtest["moving_average_7_policy_forecast"] = backtest["rolling_mean_7"].clip(
        lower=0.0
    )
    backtest["moving_average_28_policy_forecast"] = backtest["rolling_mean_28"].clip(
        lower=0.0
    )
    if statsforecast_predictions is not None:
        backtest["statsforecast_policy_forecast"] = np.maximum(
            np.asarray(statsforecast_predictions, dtype=float),
            0.0,
        )
    return backtest


def _available_baseline_policies(
    backtest: pd.DataFrame,
    configured_policies: list[str],
) -> dict[str, str]:
    policies: dict[str, str] = {}
    for policy in configured_policies:
        col = f"{policy}_policy_forecast"
        if col in backtest.columns:
            policies[policy] = col
    if len(policies) < 2:
        warnings.warn(
            "Fewer than two cost baselines are available; cost comparison is weak",
            stacklevel=2,
        )
    return policies


def _reduction_pct(baseline_total: float, optimized_total: float) -> float:
    if baseline_total <= 0:
        return 0.0
    return float(((baseline_total - optimized_total) / baseline_total) * 100.0)


def _simulate_one_cost_scenario(
    backtest: pd.DataFrame,
    *,
    baseline_policies: dict[str, str],
    understock: pd.Series,
    overstock: pd.Series,
    available_alphas: list[float],
) -> dict[str, Any]:
    _, selected_alphas, selected_forecasts = _select_newsvendor_forecast(
        backtest,
        understock=understock,
        overstock=overstock,
        available_alphas=available_alphas,
    )
    selected_forecast = pd.Series(selected_forecasts, index=backtest.index)
    actual = backtest[TARGET_COLUMN]

    optimized_total = simulated_inventory_cost(
        actual,
        selected_forecast,
        understock,
        overstock,
    )
    baseline_totals = {
        name: simulated_inventory_cost(actual, backtest[col], understock, overstock)
        for name, col in baseline_policies.items()
    }
    best_baseline_name = min(baseline_totals, key=baseline_totals.get)
    best_baseline_total = baseline_totals[best_baseline_name]
    reductions = {
        name: _reduction_pct(total, optimized_total)
        for name, total in baseline_totals.items()
    }

    return {
        "optimized_total_cost": optimized_total,
        "baseline_total_costs": baseline_totals,
        "cost_reduction_pct_by_baseline": reductions,
        "best_baseline": best_baseline_name,
        "best_baseline_total_cost": best_baseline_total,
        "cost_reduction_vs_best_baseline_pct": _reduction_pct(
            best_baseline_total,
            optimized_total,
        ),
        "optimized_cost_lt_best_baseline": bool(optimized_total < best_baseline_total),
        "median_selected_quantile_alpha": float(np.median(selected_alphas)),
    }


def _simulate_cost_metrics(
    backtest: pd.DataFrame,
    *,
    baseline_policy_names: list[str],
    available_alphas: list[float],
    sensitivity_ratios: dict[str, float],
    large_reduction_warning_threshold_pct: float,
) -> dict[str, Any]:
    baseline_policies = _available_baseline_policies(backtest, baseline_policy_names)
    if not baseline_policies:
        raise RuntimeError("No cost baselines are available")

    main = _simulate_one_cost_scenario(
        backtest,
        baseline_policies=baseline_policies,
        understock=backtest["understock_cost_per_unit"],
        overstock=backtest["overstock_cost_per_unit"],
        available_alphas=available_alphas,
    )

    sensitivity: dict[str, Any] = {}
    for label, ratio in sensitivity_ratios.items():
        overstock = backtest["overstock_cost_per_unit"]
        understock = overstock * float(ratio)
        sensitivity[label] = {
            "understock_to_overstock_ratio": float(ratio),
            **_simulate_one_cost_scenario(
                backtest,
                baseline_policies=baseline_policies,
                understock=understock,
                overstock=overstock,
                available_alphas=available_alphas,
            ),
        }

    warnings_list: list[str] = []
    if (
        main["cost_reduction_vs_best_baseline_pct"]
        >= large_reduction_warning_threshold_pct
    ):
        warnings_list.append(
            "large synthetic improvement; sensitive to baseline and cost assumptions"
        )

    lag_7_total = main["baseline_total_costs"].get("lag_7")
    lag_7_reduction = main["cost_reduction_pct_by_baseline"].get("lag_7")

    return {
        **main,
        "baseline_policies": sorted(baseline_policies),
        "baseline_count": len(baseline_policies),
        "sensitivity_by_understock_to_overstock_ratio": sensitivity,
        "warnings": warnings_list,
        "selected_pinball_loss": pinball_loss(
            backtest[TARGET_COLUMN],
            backtest["selected_quantile_forecast"],
            backtest["newsvendor_quantile"],
        ),
        # Backward-compatible aliases for the original PR-04 lag-7 comparison.
        "naive_total_cost": lag_7_total,
        "cost_reduction_pct": main["cost_reduction_vs_best_baseline_pct"],
        "lag_7_cost_reduction_pct": lag_7_reduction,
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
        metric_df = interval_df.loc[valid].copy()
        metric_df["demand_pattern"] = metric_df["part_id"].map(parts_patterns)
        metrics = interval_coverage_metrics(
            metric_df,
            actual_col="y",
            lower_col="yhat_lower",
            upper_col="yhat_upper",
            group_col="demand_pattern",
        )
        return {
            "enabled": True,
            "level": level,
            "method": "statsforecast_native_conformal_reference",
            "coverage": metrics["coverage"],
            "average_width": metrics["average_width"],
            "by_demand_pattern": metrics.get("by_demand_pattern", {}),
            "rows": metrics["rows"],
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
    cost_baseline_policies = list(decision_cfg["cost"].get("baseline_policies", []))
    sensitivity_ratios = {
        str(k): float(v)
        for k, v in decision_cfg["cost"]
        .get("sensitivity_understock_to_overstock_ratios", {})
        .items()
    }
    large_reduction_threshold = float(
        decision_cfg["cost"].get("large_reduction_warning_threshold_pct", 50.0)
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
        sf_cfg = config.get("statsforecast", {})
        statsforecast_predictions: np.ndarray | None = None
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                statsforecast_predictions, _ = fit_predict_statsforecast(
                    train_df,
                    test_df,
                    parts_patterns,
                    season_length=sf_cfg.get("season_length", 7),
                    regular_model_names=sf_cfg.get("regular_models"),
                    intermittent_model_names=sf_cfg.get("intermittent_models"),
                )
        except Exception as exc:
            logger.warning("StatsForecast cost baseline skipped: %s", exc)
            if "statsforecast" in cost_baseline_policies:
                cost_baseline_policies.remove("statsforecast")

        backtest = _build_backtest_frame(
            test_df,
            quantile_predictions,
            statsforecast_predictions,
            parts_metadata,
            available_alphas=alphas,
            holding_cost_rate=holding_cost_rate,
            understock_cost_multiplier=understock_multiplier,
        )
        raw_interval_metrics = interval_coverage_metrics(
            backtest,
            actual_col=TARGET_COLUMN,
            lower_col="raw_prediction_lower",
            upper_col="raw_prediction_upper",
            group_col="demand_pattern",
        )
        raw_interval_metrics.update(
            {
                "method": "lightgbm_quantile_p10_p90",
                "nominal_coverage_target": 0.80,
            }
        )
        backtest, calibrated_interval_metrics = _apply_calibrated_intervals(
            backtest,
            decision_cfg["interval_calibration"],
        )
        cost_metrics = _simulate_cost_metrics(
            backtest,
            baseline_policy_names=cost_baseline_policies,
            available_alphas=alphas,
            sensitivity_ratios=sensitivity_ratios,
            large_reduction_warning_threshold_pct=large_reduction_threshold,
        )

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
            "interval_metrics": {
                "nominal_coverage_target": calibrated_interval_metrics[
                    "nominal_coverage_target"
                ],
                "realized_coverage_overall": calibrated_interval_metrics["coverage"],
                "realized_coverage_by_demand_pattern": calibrated_interval_metrics.get(
                    "by_demand_pattern",
                    {},
                ),
                "average_interval_width": calibrated_interval_metrics[
                    "average_width"
                ],
                "coverage_width_tradeoff_notes": calibrated_interval_metrics[
                    "coverage_width_tradeoff_notes"
                ],
                "calibrated_empirical": calibrated_interval_metrics,
                "lightgbm_quantile_reference": raw_interval_metrics,
            },
            "statsforecast_interval_reference": sf_reference,
            "warnings": cost_metrics["warnings"],
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
                    "lag_7_total_cost": float(cost_metrics["naive_total_cost"]),
                    "optimized_total_cost": float(cost_metrics["optimized_total_cost"]),
                    "cost_reduction_pct": float(cost_metrics["cost_reduction_pct"]),
                    "cost_reduction_vs_best_baseline_pct": float(
                        cost_metrics["cost_reduction_vs_best_baseline_pct"]
                    ),
                    "selected_pinball_loss": float(
                        cost_metrics["selected_pinball_loss"]
                    ),
                    "calibrated_interval_coverage": float(
                        calibrated_interval_metrics["coverage"]
                    ),
                    "calibrated_interval_average_width": float(
                        calibrated_interval_metrics["average_width"]
                    ),
                    "raw_lightgbm_interval_coverage": float(
                        raw_interval_metrics["coverage"]
                    ),
                    "raw_lightgbm_interval_average_width": float(
                        raw_interval_metrics["average_width"]
                    ),
                }
            )
            for name, total in cost_metrics["baseline_total_costs"].items():
                mlflow.log_metric(f"{name}_total_cost", float(total))
            for name, reduction in cost_metrics[
                "cost_reduction_pct_by_baseline"
            ].items():
                mlflow.log_metric(
                    f"cost_reduction_vs_{name}_pct",
                    float(reduction),
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
