"""Tests for the deterministic champion/challenger comparison."""

from __future__ import annotations

import json

from mlops.comparison import (
    DECISION_KEEP,
    DECISION_MANUAL,
    DECISION_PROMOTE,
    compare_models,
    extract_model_metrics,
    load_pr04_context,
)


def _compare(champ_mae, chal_mae, **kwargs):
    return compare_models(
        {"mae": champ_mae},
        {"mae": chal_mae},
        primary_metric="mae",
        **kwargs,
    )


def test_close_metrics_force_manual_review():
    # PR-03 model card values: LightGBM 2.113 vs StatsForecast 2.088 (~1.2%).
    result = _compare(2.113, 2.088, decision_threshold_pct=5.0)
    assert result["decision"] == DECISION_MANUAL


def test_clear_challenger_improvement_promotes():
    result = _compare(2.0, 1.5, decision_threshold_pct=5.0)
    assert result["decision"] == DECISION_PROMOTE
    assert result["comparison"]["relative_improvement_pct"] > 5.0


def test_clear_champion_advantage_keeps():
    result = _compare(1.5, 2.0, decision_threshold_pct=5.0)
    assert result["decision"] == DECISION_KEEP
    assert result["comparison"]["relative_improvement_pct"] < -5.0


def test_missing_metric_is_manual_review():
    result = compare_models(
        {"mae": 2.0}, {"mae": None}, primary_metric="mae"
    )
    assert result["decision"] == DECISION_MANUAL
    assert result["warnings"]


def test_comparison_is_deterministic():
    a = _compare(2.0, 1.5)
    b = _compare(2.0, 1.5)
    assert a == b


def test_higher_is_better_direction():
    result = compare_models(
        {"r2": 0.5},
        {"r2": 0.8},
        primary_metric="r2",
        primary_metric_direction="higher_is_better",
        decision_threshold_pct=5.0,
    )
    assert result["decision"] == DECISION_PROMOTE


def test_extract_model_metrics_handles_missing():
    run_metrics = {
        "lightgbm_mae": 2.1,
        "lightgbm_rmse": 3.1,
        "lightgbm_mape": 26.4,
        "statsforecast_mae": 2.0,
    }
    champ = extract_model_metrics(run_metrics, "lightgbm")
    chal = extract_model_metrics(run_metrics, "statsforecast")
    assert champ == {"mae": 2.1, "rmse": 3.1, "mape": 26.4}
    assert chal["mae"] == 2.0
    assert chal["rmse"] is None
    assert chal["mape"] is None


def test_load_pr04_context_missing_file(tmp_path):
    context = load_pr04_context(tmp_path / "nope.json")
    assert context["available"] is False
    assert context["warnings"]


def test_load_pr04_context_does_not_mutate_file(tmp_path):
    path = tmp_path / "decision_summary.json"
    original = {
        "test_period": "2024-10-07 to 2024-12-30",
        "cost_metrics": {
            "selected_pinball_loss": 1.23,
            "cost_reduction_vs_best_baseline_pct": 4.5,
        },
    }
    path.write_text(json.dumps(original, indent=2), encoding="utf-8")
    before = path.read_bytes()

    context = load_pr04_context(path)

    assert context["available"] is True
    assert context["synthetic"] is True
    assert context["selected_pinball_loss"] == 1.23
    # Read-only: the PR-04 metric file must be byte-for-byte unchanged.
    assert path.read_bytes() == before
