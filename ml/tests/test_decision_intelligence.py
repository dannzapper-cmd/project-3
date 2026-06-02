"""Tests for PR-04 decision intelligence."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from ml.decision import (
    calculate_eoq,
    calculate_reorder_point,
    calculate_safety_stock,
    enforce_prediction_interval_monotonicity,
    newsvendor_quantile,
    pinball_loss,
    risk_level,
    service_level_to_z_score,
    stockout_risk_normal,
    validate_forecast_feature_columns,
)
from ml.decision_intelligence import run_decision_intelligence
from ml.features import build_features, drop_rows_with_incomplete_features
from ml.models.lightgbm_model import train_quantile_models
from ml.split import temporal_train_test_split


def test_safety_stock_formula():
    z_score = service_level_to_z_score(0.95)
    assert z_score == pytest.approx(1.6448536269514722)
    assert calculate_safety_stock(z_score, 2.0, 9.0) == pytest.approx(
        z_score * 2.0 * 3.0
    )


def test_reorder_point_formula():
    assert calculate_reorder_point(40.0, 12.5) == pytest.approx(52.5)


def test_eoq_formula_normal_and_invalid_inputs():
    assert calculate_eoq(1000.0, 50.0, 2.0) == pytest.approx(
        math.sqrt((2.0 * 1000.0 * 50.0) / 2.0)
    )
    with pytest.warns(UserWarning, match="Cannot compute EOQ"):
        assert math.isnan(calculate_eoq(1000.0, 0.0, 2.0))


def test_prediction_interval_monotonicity():
    raw = pd.DataFrame({"q10": [10.0, 5.0], "q50": [8.0, 7.0], "q90": [9.0, 6.0]})
    intervals = enforce_prediction_interval_monotonicity(raw)
    assert (intervals["prediction_lower"] <= intervals["prediction"]).all()
    assert (intervals["prediction"] <= intervals["prediction_upper"]).all()


def test_stockout_risk_bounded_and_thresholds():
    risk = stockout_risk_normal(
        forecast_mean_daily=10.0,
        demand_std_daily=2.0,
        lead_time_days=4.0,
        current_stock=35.0,
    )
    assert 0.0 <= risk <= 1.0
    assert risk_level(0.19) == "low"
    assert risk_level(0.20) == "medium"
    assert risk_level(0.50) == "medium"
    assert risk_level(0.51) == "high"


def test_newsvendor_quantile_and_pinball_loss():
    assert newsvendor_quantile(8.0, 2.0) == pytest.approx(0.8)
    assert pinball_loss([10.0, 5.0], [8.0, 7.0], 0.8) == pytest.approx(1.0)


def test_anti_leakage_guard_rejects_decision_fields(demand_table):
    forbidden = ["current_stock", "reorder_point", "safety_stock", "unit_cost"]
    for col in forbidden:
        assert col not in demand_table.columns

    with pytest.raises(ValueError, match="Decision/inventory fields"):
        validate_forecast_feature_columns(["lag_7", "unit_cost"])


def test_quantile_models_can_exclude_lead_time(demand_table):
    featured = drop_rows_with_incomplete_features(build_features(demand_table))
    train_df, _ = temporal_train_test_split(featured, train_fraction=0.75)
    small_items = sorted(train_df["part_id"].unique())[:4]
    small_train = train_df[train_df["part_id"].isin(small_items)]

    _, features = train_quantile_models(
        small_train,
        {"n_estimators": 5, "random_state": 42, "verbose": -1},
        alphas=[0.1, 0.5, 0.9],
        excluded_features=["lead_time_days"],
    )

    assert "lead_time_days" not in features
    validate_forecast_feature_columns(features)


@pytest.fixture
def decision_config(tmp_path, synthetic_dir) -> dict:
    config = yaml.safe_load(Path("ml/config.yaml").read_text(encoding="utf-8"))
    config["data"]["synthetic_dir"] = str(synthetic_dir)
    config["mlflow"]["tracking_uri"] = str(tmp_path / "mlruns")
    config["lightgbm"]["n_estimators"] = 20
    config["decision"]["artifact_dir"] = str(tmp_path / "artifacts" / "decision")
    config["decision"]["mlflow"]["enabled"] = False
    config["decision"]["statsforecast_interval_reference"]["enabled"] = False
    config["decision"]["cost"]["large_reduction_warning_threshold_pct"] = 0.0
    config["decision"]["policy_optimization"][
        "large_reduction_warning_threshold_pct"
    ] = 0.0
    return config


@pytest.fixture
def decision_result(decision_config) -> dict:
    return run_decision_intelligence(decision_config, max_items=12, max_days=90)


def test_decision_artifact_schema_and_bounds(decision_result):
    recommendations = pd.read_csv(
        decision_result["artifacts"]["recommendations_csv"],
    )
    expected_columns = {
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
        "safety_stock",
        "reorder_point",
        "eoq",
        "stockout_risk",
        "risk_level",
        "newsvendor_quantile",
        "selected_quantile_alpha",
    }
    assert expected_columns.issubset(recommendations.columns)
    assert (recommendations["prediction_lower"] <= recommendations["prediction"]).all()
    assert (recommendations["prediction"] <= recommendations["prediction_upper"]).all()
    assert recommendations["stockout_risk"].between(0.0, 1.0).all()
    assert set(recommendations["risk_level"]).issubset({"low", "medium", "high"})


def test_interval_metrics_are_bounded_and_non_negative(decision_result):
    metrics = decision_result["interval_metrics"]
    calibrated = metrics["calibrated_empirical"]

    assert metrics["nominal_coverage_target"] == pytest.approx(0.90)
    assert 0.0 <= metrics["realized_coverage_overall"] <= 1.0
    assert metrics["average_interval_width"] >= 0.0
    assert 0.0 <= calibrated["coverage"] <= 1.0
    assert calibrated["average_width"] >= 0.0

    for pattern_metrics in metrics["realized_coverage_by_demand_pattern"].values():
        assert 0.0 <= pattern_metrics["coverage"] <= 1.0
        assert pattern_metrics["average_width"] >= 0.0


def test_cost_metrics_include_multiple_baselines_and_warning(decision_result):
    metrics = decision_result["cost_metrics"]
    assert metrics["baseline_count"] >= 2
    assert len(metrics["baseline_total_costs"]) >= 2
    assert "lag_7" in metrics["baseline_total_costs"]
    assert "moving_average_7" in metrics["baseline_total_costs"]
    assert metrics["optimized_total_cost"] < metrics["best_baseline_total_cost"]
    assert metrics["cost_reduction_vs_best_baseline_pct"] > 0.0
    assert (
        "large synthetic improvement; sensitive to baseline and cost assumptions"
        in metrics["warnings"]
    )
    assert metrics["sensitivity_by_understock_to_overstock_ratio"]


def test_policy_optimization_is_deterministic(decision_config, decision_result):
    repeat = run_decision_intelligence(decision_config, max_items=12, max_days=90)
    assert (
        repeat["policy_optimization"]["selected_policy_by_demand_pattern"]
        == decision_result["policy_optimization"]["selected_policy_by_demand_pattern"]
    )
    assert repeat["policy_optimization"]["headline"] == decision_result[
        "policy_optimization"
    ]["headline"]


def test_policy_parameters_are_from_configured_grid(decision_config, decision_result):
    policy = decision_result["policy_optimization"]
    grid = decision_config["decision"]["policy_optimization"]
    service_levels = set(grid["service_level_candidates"])
    safety_multipliers = set(grid["safety_stock_multiplier_candidates"])
    order_multipliers = set(grid["order_quantity_multiplier_candidates"])

    assert policy["optimization_level"] == "demand_pattern"
    assert policy["selected_policy_by_demand_pattern"]
    for params in policy["selected_policy_by_demand_pattern"].values():
        assert params["service_level"] in service_levels
        assert params["safety_stock_multiplier"] in safety_multipliers
        assert params["order_quantity_multiplier"] in order_multipliers


def test_policy_optimization_keeps_forecasts_and_intervals_unchanged(decision_result):
    policy = decision_result["policy_optimization"]
    intervals = decision_result["interval_metrics"]["calibrated_empirical"]

    assert policy["forecast_predictions_unchanged"] is True
    assert policy["forecast_prediction_checksum_before"] == pytest.approx(
        policy["forecast_prediction_checksum_after"]
    )
    assert policy["calibrated_interval_reference"]["coverage"] == pytest.approx(
        intervals["coverage"]
    )
    assert policy["calibrated_interval_reference"]["average_width"] == pytest.approx(
        intervals["average_width"]
    )


def test_policy_reports_split_metrics_and_sensitivity(decision_result):
    policy = decision_result["policy_optimization"]
    scenarios = policy["evaluation"]

    assert policy["policy_calibration_rows"] > 0
    assert policy["policy_evaluation_rows"] > 0
    assert policy["policy_calibration_period"] != policy["policy_evaluation_period"]
    assert set(scenarios) == {"low", "medium", "high"}

    for metrics in scenarios.values():
        assert np.isfinite(metrics["cost_reduction_vs_fixed_formula_pct"])
        assert np.isfinite(metrics["cost_reduction_vs_best_baseline_pct"])
        for total in metrics["policy_total_costs"].values():
            assert np.isfinite(total)
            assert total >= 0.0


def test_policy_governance_warnings(decision_result):
    warnings = decision_result["policy_optimization"]["warnings"]
    assert any("synthetic policy improvement" in warning for warning in warnings)
