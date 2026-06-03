"""Schema-stability tests for retraining summary / rollback / error artifacts."""

from __future__ import annotations

from mlops.retraining import ROLLBACK_SCHEMA_VERSION, SUMMARY_SCHEMA_VERSION
from mlops.retraining.summary import (
    ROLLBACK_REQUIRED_FIELDS,
    SUMMARY_REQUIRED_FIELDS,
    build_error_analysis,
    build_rollback_manifest,
    build_summary,
    validate_required_fields,
)

_COMPARISON = {
    "candidate_metric": 1.5,
    "champion_metric": 2.0,
    "metric_direction": "lower_is_better",
    "absolute_delta": -0.5,
    "relative_delta_pct": 25.0,
    "promotion_threshold": 5.0,
    "promoted": True,
}


def _summary(**overrides):
    base = dict(
        run_id="abc",
        git_commit="deadbeef",
        mode="smoke",
        model_name="demand_forecast",
        primary_metric="mae",
        metric_direction="lower_is_better",
        comparison=_COMPARISON,
        status="promoted",
        promoted=True,
        first_run=False,
        rejected_reason=None,
        failure_reason=None,
        rollback_target="1",
        data_reference={"rows": 10},
        config_reference={"mode": "smoke"},
        bentoml_artifact=None,
    )
    base.update(overrides)
    return build_summary(**base)


def test_summary_has_all_required_fields():
    summary = _summary()
    assert validate_required_fields(summary, SUMMARY_REQUIRED_FIELDS) == []
    assert summary["schema_version"] == SUMMARY_SCHEMA_VERSION


def test_summary_field_types():
    summary = _summary()
    assert isinstance(summary["promoted"], bool)
    assert isinstance(summary["first_run"], bool)
    assert isinstance(summary["candidate_metric"], (int, float))
    assert isinstance(summary["warnings"], list)


def test_failed_summary_keeps_required_fields_as_null_not_zero():
    # Failed run: metrics were never computed -> null, never a fake 0.0.
    empty_comparison = {
        "candidate_metric": None,
        "champion_metric": None,
        "metric_direction": "lower_is_better",
        "absolute_delta": None,
        "relative_delta_pct": None,
        "promotion_threshold": 5.0,
        "promoted": False,
    }
    summary = _summary(
        comparison=empty_comparison,
        status="failed",
        promoted=False,
        failure_reason="boom",
        rollback_target=None,
    )
    assert validate_required_fields(summary, SUMMARY_REQUIRED_FIELDS) == []
    assert summary["candidate_metric"] is None
    assert summary["champion_metric"] is None
    assert summary["absolute_delta"] is None
    assert summary["failure_reason"] == "boom"
    assert summary["promoted"] is False


def test_rollback_manifest_has_all_required_fields():
    manifest = build_rollback_manifest(
        champion_before={"version": "1"},
        champion_after={"version": "1"},
        candidate_run_id="abc",
        rollback_target="1",
        rollback_method="mlflow_alias",
        metrics_before={"mae": 2.0},
        metrics_after={"mae": 1.5},
    )
    assert validate_required_fields(manifest, ROLLBACK_REQUIRED_FIELDS) == []
    assert manifest["schema_version"] == ROLLBACK_SCHEMA_VERSION
    assert manifest["dry_run_available"] is True


def test_rollback_method_is_constrained_value():
    manifest = build_rollback_manifest(
        champion_before=None,
        champion_after=None,
        candidate_run_id=None,
        rollback_target=None,
        rollback_method="manifest_only",
        metrics_before=None,
        metrics_after=None,
    )
    assert manifest["rollback_method"] in {"mlflow_alias", "manifest_only"}
    # Unknown values are null, not omitted.
    assert manifest["rollback_target"] is None
    assert manifest["candidate_run_id"] is None


def test_error_analysis_schema():
    payload = build_error_analysis(
        available=True,
        worst_items_by_error=[{"part_id": "P1", "mean_abs_error": 3.2}],
    )
    assert payload["available"] is True
    assert payload["worst_items_by_error"][0]["part_id"] == "P1"
    assert "notes" in payload
