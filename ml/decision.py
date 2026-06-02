"""Decision intelligence formulas for inventory recommendations."""

from __future__ import annotations

import math
import warnings
from collections.abc import Iterable

import numpy as np
import pandas as pd
from scipy.stats import norm

FORBIDDEN_DECISION_FEATURES: frozenset[str] = frozenset(
    {
        "current_stock",
        "reorder_point",
        "safety_stock",
        "unit_cost",
        "order_cost",
        "annual_holding_cost_per_unit",
        "stockout_flag",
    }
)


def validate_forecast_feature_columns(
    feature_columns: Iterable[str],
    *,
    forbidden: Iterable[str] = FORBIDDEN_DECISION_FEATURES,
) -> None:
    """Raise if inventory decision fields leak into demand forecast features."""

    used_forbidden = sorted(set(feature_columns).intersection(forbidden))
    if used_forbidden:
        raise ValueError(
            "Decision/inventory fields must not be used as demand forecast "
            f"features: {used_forbidden}"
        )


def service_level_to_z_score(service_level: float) -> float:
    """Convert service level to a Normal z-score."""

    if not 0.0 < service_level < 1.0:
        raise ValueError("service_level must be between 0 and 1")
    return float(norm.ppf(service_level))


def calculate_safety_stock(
    z_score: float,
    demand_std: float,
    lead_time_days: float,
) -> float:
    """Safety stock with fixed lead time and demand variance only."""

    if not math.isfinite(demand_std) or demand_std < 0:
        warnings.warn("Invalid demand_std received; using 0.0", stacklevel=2)
        demand_std = 0.0
    if not math.isfinite(lead_time_days) or lead_time_days <= 0:
        warnings.warn("Invalid lead_time_days received; using 0.0", stacklevel=2)
        return 0.0
    return float(z_score * demand_std * math.sqrt(lead_time_days))


def calculate_reorder_point(
    demand_during_lead_time: float,
    safety_stock: float,
) -> float:
    """Reorder point equals lead-time demand plus safety stock."""

    return float(max(demand_during_lead_time, 0.0) + max(safety_stock, 0.0))


def calculate_eoq(
    annual_demand: float,
    order_cost: float,
    annual_holding_cost_per_unit: float,
) -> float:
    """Economic order quantity with invalid inputs converted to NaN warnings."""

    invalid: list[str] = []
    if not math.isfinite(annual_demand) or annual_demand <= 0:
        invalid.append("annual_demand")
    if not math.isfinite(order_cost) or order_cost <= 0:
        invalid.append("order_cost")
    if (
        not math.isfinite(annual_holding_cost_per_unit)
        or annual_holding_cost_per_unit <= 0
    ):
        invalid.append("annual_holding_cost_per_unit")
    if invalid:
        warnings.warn(
            f"Cannot compute EOQ with non-positive inputs: {', '.join(invalid)}",
            stacklevel=2,
        )
        return float("nan")
    return float(
        math.sqrt((2.0 * annual_demand * order_cost) / annual_holding_cost_per_unit)
    )


def enforce_prediction_interval_monotonicity(
    predictions: pd.DataFrame,
    *,
    lower_col: str = "q10",
    prediction_col: str = "q50",
    upper_col: str = "q90",
) -> pd.DataFrame:
    """Return lower/prediction/upper columns with monotonic quantile ordering."""

    required = [lower_col, prediction_col, upper_col]
    missing = [col for col in required if col not in predictions.columns]
    if missing:
        raise ValueError(f"Missing prediction interval columns: {missing}")

    values = predictions[required].clip(lower=0.0)
    lower = values.min(axis=1)
    upper = values.max(axis=1)
    prediction = values[prediction_col].clip(lower=lower, upper=upper)

    return pd.DataFrame(
        {
            "prediction_lower": lower,
            "prediction": prediction,
            "prediction_upper": upper,
        },
        index=predictions.index,
    )


def interval_coverage_metrics(
    frame: pd.DataFrame,
    *,
    actual_col: str,
    lower_col: str,
    upper_col: str,
    group_col: str | None = None,
) -> dict[str, object]:
    """Compute coverage and interval width overall and optionally by group."""

    required = [actual_col, lower_col, upper_col]
    if group_col:
        required.append(group_col)
    missing = [col for col in required if col not in frame.columns]
    if missing:
        raise ValueError(f"Missing interval metric columns: {missing}")

    valid = frame[required].dropna().copy()
    if valid.empty:
        return {"coverage": float("nan"), "average_width": float("nan"), "rows": 0}

    width = (valid[upper_col] - valid[lower_col]).clip(lower=0.0)
    covered = (valid[actual_col] >= valid[lower_col]) & (
        valid[actual_col] <= valid[upper_col]
    )
    metrics: dict[str, object] = {
        "coverage": float(covered.mean()),
        "average_width": float(width.mean()),
        "rows": int(len(valid)),
    }

    if group_col:
        grouped: dict[str, dict[str, float | int]] = {}
        working = valid.assign(_covered=covered, _width=width)
        for group, group_df in working.groupby(group_col, observed=True):
            grouped[str(group)] = {
                "coverage": float(group_df["_covered"].mean()),
                "average_width": float(group_df["_width"].mean()),
                "rows": int(len(group_df)),
            }
        metrics["by_demand_pattern"] = grouped

    return metrics


def stockout_risk_normal(
    forecast_mean_daily: float,
    demand_std_daily: float,
    lead_time_days: float,
    current_stock: float,
) -> float:
    """Estimate P(demand during fixed lead time exceeds current stock)."""

    if not math.isfinite(lead_time_days) or lead_time_days <= 0:
        warnings.warn("Invalid lead_time_days received; stockout risk=0", stacklevel=2)
        return 0.0
    if not math.isfinite(current_stock) or current_stock < 0:
        warnings.warn("Invalid current_stock received; using 0.0", stacklevel=2)
        current_stock = 0.0
    if not math.isfinite(demand_std_daily) or demand_std_daily < 0:
        warnings.warn("Invalid demand_std_daily received; using 0.0", stacklevel=2)
        demand_std_daily = 0.0
    if not math.isfinite(forecast_mean_daily):
        warnings.warn("Invalid forecast_mean_daily received; using 0.0", stacklevel=2)
        forecast_mean_daily = 0.0

    mean_demand_lt = max(forecast_mean_daily, 0.0) * lead_time_days
    std_demand_lt = demand_std_daily * math.sqrt(lead_time_days)
    if std_demand_lt <= 0:
        return float(mean_demand_lt > current_stock)

    risk = 1.0 - float(norm.cdf(current_stock, loc=mean_demand_lt, scale=std_demand_lt))
    return float(np.clip(risk, 0.0, 1.0))


def risk_level(
    risk: float,
    *,
    low_threshold: float = 0.20,
    high_threshold: float = 0.50,
) -> str:
    """Map stockout probability to low/medium/high buckets."""

    if risk < low_threshold:
        return "low"
    if risk > high_threshold:
        return "high"
    return "medium"


def newsvendor_quantile(
    understock_cost: float,
    overstock_cost: float,
) -> float:
    """Optimal newsvendor quantile Cu / (Cu + Co)."""

    if understock_cost < 0 or overstock_cost < 0:
        warnings.warn("Negative newsvendor cost received; using 0.5", stacklevel=2)
        return 0.5
    total = understock_cost + overstock_cost
    if total <= 0:
        warnings.warn("Zero newsvendor costs received; using 0.5", stacklevel=2)
        return 0.5
    return float(np.clip(understock_cost / total, 0.0, 1.0))


def pinball_loss(
    actual: float | np.ndarray | pd.Series,
    forecast: float | np.ndarray | pd.Series,
    quantile: float | np.ndarray | pd.Series,
) -> float:
    """Mean pinball loss for a forecast quantile."""

    quantile_arr = np.asarray(quantile, dtype=float)
    if np.any((quantile_arr < 0.0) | (quantile_arr > 1.0)):
        raise ValueError("quantile must be between 0 and 1")
    actual_arr = np.asarray(actual, dtype=float)
    forecast_arr = np.asarray(forecast, dtype=float)
    error = actual_arr - forecast_arr
    loss = np.maximum(quantile_arr * error, (quantile_arr - 1.0) * error)
    return float(np.mean(loss))


def simulated_inventory_cost(
    actual: float | np.ndarray | pd.Series,
    policy_quantity: float | np.ndarray | pd.Series,
    understock_cost_per_unit: float | np.ndarray | pd.Series,
    overstock_cost_per_unit: float | np.ndarray | pd.Series,
) -> float:
    """Total synthetic holding plus stockout cost for one backtest policy."""

    actual_arr = np.asarray(actual, dtype=float)
    policy_arr = np.asarray(policy_quantity, dtype=float)
    understock_arr = np.maximum(np.asarray(understock_cost_per_unit, dtype=float), 0.0)
    overstock_arr = np.maximum(np.asarray(overstock_cost_per_unit, dtype=float), 0.0)

    shortage = np.maximum(actual_arr - policy_arr, 0.0)
    overage = np.maximum(policy_arr - actual_arr, 0.0)
    return float(np.sum(shortage * understock_arr + overage * overstock_arr))


def nearest_quantile_alpha(
    target_quantile: float,
    available_alphas: Iterable[float],
) -> float:
    """Return the available alpha closest to the target newsvendor quantile."""

    alphas = [float(alpha) for alpha in available_alphas]
    if not alphas:
        raise ValueError("At least one quantile alpha is required")
    return min(alphas, key=lambda alpha: abs(alpha - target_quantile))
