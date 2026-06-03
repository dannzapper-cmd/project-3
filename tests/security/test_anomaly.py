"""Anomaly detection determinism and guard tests."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from security.anomaly import AnomalyDetector
from security.constants import (
    ANOMALY_FEATURES,
    FEATURES_USED_STRING,
    MIN_SAMPLES_FOR_ANOMALY,
    RANDOM_STATE,
)
from security.audit import AuditLogger

FIXTURE = Path(__file__).parent / "fixtures" / "demo_movements.csv"


@pytest.fixture
def demo_movements() -> pd.DataFrame:
    return pd.read_csv(FIXTURE)


def test_anomaly_detection_is_deterministic(demo_movements: pd.DataFrame) -> None:
    first = AnomalyDetector(demo_movements).detect()
    second = AnomalyDetector(demo_movements).detect()
    pd.testing.assert_frame_equal(first, second)


def test_anomaly_results_columns(demo_movements: pd.DataFrame) -> None:
    result = AnomalyDetector(demo_movements).detect()
    expected_cols = {
        "movement_id",
        "part_id",
        "date",
        "quantity",
        "anomaly_score",
        "is_anomaly",
        "features_used",
    }
    assert set(result.columns) == expected_cols
    assert result["features_used"].iloc[0] == FEATURES_USED_STRING
    assert set(result["is_anomaly"].unique()).issubset({0, 1})


def test_insufficient_samples_guard(tmp_path: Path) -> None:
    tiny = pd.DataFrame(
        {
            "movement_id": [f"MOV-{i:04d}" for i in range(5)],
            "part_id": ["P1"] * 5,
            "date": ["2024-01-01"] * 5,
            "movement_type": ["in"] * 5,
            "quantity": [1.0, 2.0, 3.0, 4.0, 5.0],
            "reference": ["PO-1000"] * 5,
        }
    )
    audit = AuditLogger(tmp_path / "audit.jsonl")
    result = AnomalyDetector(tiny, audit=audit).detect()
    assert len(result) == 5
    assert (result["is_anomaly"] == 0).all()
    assert (result["anomaly_score"] == 0.0).all()
    warnings = [
        e
        for e in audit.events
        if e["event_type"] == "SYSTEM_CHECK"
        and "Insufficient samples" in e["description"]
    ]
    assert len(warnings) == 1
    assert str(MIN_SAMPLES_FOR_ANOMALY) in warnings[0]["description"]


def test_features_used_match_constants() -> None:
    assert FEATURES_USED_STRING == "|".join(ANOMALY_FEATURES)


def test_random_state_constant() -> None:
    assert RANDOM_STATE == 42
