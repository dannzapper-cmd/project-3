"""End-to-end pipeline and artifact generation tests."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from security.constants import FORBIDDEN_ARTIFACT_SUBSTRINGS
from security.pipeline import run_security_pipeline

FIXTURE = Path(__file__).parent / "fixtures" / "demo_movements.csv"


@pytest.fixture
def pipeline_dirs(tmp_path: Path) -> tuple[Path, Path]:
    data_dir = tmp_path / "synthetic"
    data_dir.mkdir()
    shutil.copy(FIXTURE, data_dir / "stock_movements.csv")
    out_dir = tmp_path / "security"
    return data_dir, out_dir


def test_pipeline_generates_four_artifacts(pipeline_dirs: tuple[Path, Path]) -> None:
    data_dir, out_dir = pipeline_dirs
    paths = run_security_pipeline(output_dir=out_dir, data_dir=data_dir)

    assert paths["audit_log"].is_file()
    assert paths["risk_score_summary"].is_file()
    assert paths["anomaly_results"].is_file()
    assert paths["security_summary"].is_file()


def test_security_summary_schema(pipeline_dirs: tuple[Path, Path]) -> None:
    data_dir, out_dir = pipeline_dirs
    run_security_pipeline(output_dir=out_dir, data_dir=data_dir)
    summary_path = out_dir / "security_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    required = {
        "generated_at",
        "period_analyzed",
        "total_events_analyzed",
        "total_anomalies_detected",
        "high_risk_events",
        "critical_risk_events",
        "top_risk_parts",
        "anomaly_rate",
        "audit_log_path",
        "model_used",
        "contamination_param",
        "random_state",
        "posture",
        "posture_reason",
    }
    assert required <= set(summary.keys())
    assert summary["posture"] in {"CLEAN", "ELEVATED", "HIGH_RISK"}
    assert summary["model_used"] == "IsolationForest"
    assert summary["random_state"] == 42


def test_risk_summary_is_array(pipeline_dirs: tuple[Path, Path]) -> None:
    data_dir, out_dir = pipeline_dirs
    run_security_pipeline(output_dir=out_dir, data_dir=data_dir)
    risk = json.loads((out_dir / "risk_score_summary.json").read_text(encoding="utf-8"))
    assert isinstance(risk, list)
    if risk:
        item = risk[0]
        for key in (
            "event_id",
            "part_id",
            "date",
            "movement_type",
            "quantity",
            "risk_score",
            "risk_level",
            "factors",
            "rule_triggered",
        ):
            assert key in item


def test_artifacts_contain_no_secret_patterns(pipeline_dirs: tuple[Path, Path]) -> None:
    data_dir, out_dir = pipeline_dirs
    run_security_pipeline(output_dir=out_dir, data_dir=data_dir)
    for path in out_dir.iterdir():
        if path.suffix not in {".json", ".jsonl", ".csv"}:
            continue
        content = path.read_text(encoding="utf-8").lower()
        for token in FORBIDDEN_ARTIFACT_SUBSTRINGS:
            assert token not in content, f"{token} found in {path.name}"
