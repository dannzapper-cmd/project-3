"""Artifact path + JSON schema tests and PR-03/PR-04 non-mutation guards."""

from __future__ import annotations

import json

from mlops.comparison import DECISION_MANUAL
from mlops.loop import run_comparison_step, run_registry_step


def _mlops_config(tracking_uri, pr04_path=None):
    cfg = {
        "mlflow": {
            "tracking_uri": tracking_uri,
            "forecast_experiment": "demand_forecast_baseline",
            "forecast_model_artifact": "lightgbm_model",
            "registered_model_name": "demand_forecast",
            "champion_alias": "champion",
            "champion_run_tag": "pr05_champion_run_id",
        },
        "champion_challenger": {
            "champion_model": "lightgbm",
            "challenger_model": "statsforecast",
            "primary_metric": "mae",
            "primary_metric_direction": "lower_is_better",
            "decision_threshold_pct": 5.0,
        },
    }
    if pr04_path is not None:
        cfg["champion_challenger"]["pr04_summary_path"] = str(pr04_path)
    return cfg


def test_comparison_step_writes_schema_and_manual_review(tmp_path):
    artifact_root = tmp_path / "artifacts" / "mlops"
    uri = f"file:{tmp_path / 'empty_mlruns'}"
    payload = run_comparison_step(
        {"split": {"train_fraction": 0.75}},
        _mlops_config(uri),
        artifact_root,
    )

    comparison_json = artifact_root / "champion_challenger" / "comparison.json"
    comparison_md = artifact_root / "champion_challenger" / "comparison.md"
    assert comparison_json.exists()
    assert comparison_md.exists()

    on_disk = json.loads(comparison_json.read_text(encoding="utf-8"))
    for key in (
        "schema_version",
        "generated_at_utc",
        "primary_metric",
        "primary_metric_direction",
        "temporal_split",
        "champion",
        "challenger",
        "comparison",
        "decision",
        "reason",
        "supporting_context",
        "warnings",
        "limitations",
    ):
        assert key in on_disk
    # No PR-03 run available -> incomplete metrics -> manual review.
    assert on_disk["decision"] == DECISION_MANUAL
    assert payload["decision"] == DECISION_MANUAL


def test_comparison_step_does_not_mutate_pr04_summary(tmp_path):
    artifact_root = tmp_path / "artifacts" / "mlops"
    uri = f"file:{tmp_path / 'empty_mlruns'}"
    pr04 = tmp_path / "decision_summary.json"
    pr04.write_text(
        json.dumps(
            {
                "test_period": "2024-10-07 to 2024-12-30",
                "cost_metrics": {"selected_pinball_loss": 1.0},
            }
        ),
        encoding="utf-8",
    )
    before = pr04.read_bytes()

    run_comparison_step(
        {"split": {"train_fraction": 0.75}},
        _mlops_config(uri, pr04_path=pr04),
        artifact_root,
    )
    assert pr04.read_bytes() == before


def test_registry_step_writes_summary_schema(tmp_path):
    artifact_root = tmp_path / "artifacts" / "mlops"
    uri = f"file:{tmp_path / 'empty_mlruns'}"
    summary = run_registry_step(
        {},
        _mlops_config(uri),
        artifact_root,
    )
    registry_json = artifact_root / "registry" / "registered_model_summary.json"
    assert registry_json.exists()
    on_disk = json.loads(registry_json.read_text(encoding="utf-8"))
    for key in (
        "schema_version",
        "generated_at_utc",
        "registry_strategy",
        "model_name",
        "champion",
        "limitations",
        "warnings",
    ):
        assert key in on_disk
    assert summary["registry_strategy"] in {"native_aliases", "tags_json_fallback"}
