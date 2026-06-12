"""Tests for PR-06 dashboard artifact loaders."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from dashboard.loaders import (
    derive_overview_status,
    derive_system_flow_steps,
    format_mtime,
    load_bentoml_build_summary,
    load_champion_challenger_comparison,
    load_decision_recommendations,
    load_decision_summary,
    load_evidently_artifact_status,
    load_mlops_loop_summary,
    load_registry_summary,
    load_synthetic_data_status,
)
from dashboard.types import LoaderResult


def _assert_contract(result: LoaderResult) -> None:
    assert result["status"] in {"ok", "missing"}
    if result["status"] == "ok":
        assert "data" in result
        assert "mtime" in result
        assert "path" in result
    else:
        assert result["reason"]
        assert isinstance(result["commands"], list)
        assert result["commands"]


def test_missing_decision_summary_returns_commands(tmp_path):
    result = load_decision_summary(tmp_path / "missing.json")
    _assert_contract(result)
    assert result["status"] == "missing"
    assert any("decision-intel" in cmd for cmd in result["commands"])


def test_decision_summary_zero_rows_is_missing(tmp_path):
    path = tmp_path / "decision_summary.json"
    path.write_text(
        json.dumps({"recommendation_rows": 0, "cost_metrics": {}}),
        encoding="utf-8",
    )
    result = load_decision_summary(path)
    assert result["status"] == "missing"


def test_decision_summary_ok(tmp_path):
    path = tmp_path / "decision_summary.json"
    path.write_text(
        json.dumps(
            {
                "test_period": "2024-01-01 to 2024-03-01",
                "recommendation_rows": 5,
                "cost_metrics": {"warnings": []},
            }
        ),
        encoding="utf-8",
    )
    result = load_decision_summary(path)
    _assert_contract(result)
    assert result["status"] == "ok"
    assert result["data"]["recommendation_rows"] == 5


def test_decision_recommendations_empty_csv_is_missing(tmp_path):
    path = tmp_path / "decision_recommendations.csv"
    path.write_text("part_id,safety_stock,reorder_point,eoq,stockout_risk,risk_level\n")
    result = load_decision_recommendations(path)
    assert result["status"] == "missing"


def test_decision_recommendations_ok(tmp_path):
    path = tmp_path / "decision_recommendations.csv"
    frame = pd.DataFrame(
        {
            "part_id": ["P1"],
            "safety_stock": [1.0],
            "reorder_point": [2.0],
            "eoq": [3.0],
            "stockout_risk": [0.5],
            "risk_level": ["medium"],
        }
    )
    frame.to_csv(path, index=False)
    result = load_decision_recommendations(path)
    assert result["status"] == "ok"
    assert len(result["data"]) == 1


def test_champion_challenger_missing_metrics_is_missing(tmp_path):
    path = tmp_path / "comparison.json"
    path.write_text(
        json.dumps(
            {
                "primary_metric": "mae",
                "champion": {"metrics": {}},
                "challenger": {"metrics": {}},
            }
        ),
        encoding="utf-8",
    )
    result = load_champion_challenger_comparison(path)
    assert result["status"] == "missing"


def test_champion_challenger_ok(tmp_path):
    path = tmp_path / "comparison.json"
    path.write_text(
        json.dumps(
            {
                "primary_metric": "mae",
                "decision": "manual_review",
                "champion": {"name": "lightgbm", "metrics": {"mae": 2.1}},
                "challenger": {"name": "statsforecast", "metrics": {"mae": 2.0}},
            }
        ),
        encoding="utf-8",
    )
    result = load_champion_challenger_comparison(path)
    assert result["status"] == "ok"


def test_mlops_and_registry_loaders_missing(tmp_path):
    for loader in (
        load_mlops_loop_summary,
        load_registry_summary,
        load_bentoml_build_summary,
    ):
        result = loader(tmp_path / "nope.json")
        _assert_contract(result)
        assert result["status"] == "missing"


def test_synthetic_data_status_with_fixture(synthetic_dir):
    result = load_synthetic_data_status(synthetic_dir)
    _assert_contract(result)
    assert result["status"] == "ok"
    assert result["data"]["ready"] is True


def test_evidently_status_missing_paths(tmp_path):
    result = load_evidently_artifact_status(
        drift_path=tmp_path / "drift.json",
        quality_path=tmp_path / "quality.json",
    )
    assert result["status"] == "missing"


def test_derive_overview_status_labels():
    missing = {"status": "missing", "reason": "x", "commands": []}
    ok = {
        "status": "ok",
        "data": {},
        "path": "/tmp/x",
        "mtime": "2024-01-01 00:00",
    }
    overview = derive_overview_status(
        synthetic=ok,
        comparison=missing,
        decision_summary=ok,
        mlops_summary=missing,
    )
    assert overview == {
        "data": "ok",
        "ml_forecast": "missing",
        "decision": "ok",
        "mlops": "missing",
    }


def test_derive_system_flow_steps_pipeline_and_companion():
    missing = {"status": "missing", "reason": "x", "commands": []}
    ok = {
        "status": "ok",
        "data": {},
        "path": "/tmp/x",
        "mtime": "2024-01-01 00:00",
    }
    steps = derive_system_flow_steps(
        synthetic=ok,
        comparison=ok,
        decision_summary=ok,
        mlops_summary=missing,
    )
    assert len(steps) == 8
    pipeline = [s for s in steps if s["kind"] == "pipeline"]
    companions = [s for s in steps if s["kind"] == "companion"]
    assert len(pipeline) == 5
    assert len(companions) == 3
    assert pipeline[0]["title"] == "Data source"
    assert companions[0]["title"] == "API health / metrics"


def test_format_mtime_missing_file():
    assert format_mtime(Path("/nonexistent/file.json")) == "Unknown"


def test_loaders_do_not_invent_values_on_missing():
    bogus = Path("/tmp/invforge-nonexistent-artifact.json")
    result = load_decision_summary(bogus)
    assert result["status"] == "missing"
    assert "data" not in result
