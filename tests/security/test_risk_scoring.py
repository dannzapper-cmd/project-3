"""Risk scoring rules, thresholds, and explainability tests."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from security.constants import (
    RISK_LEVEL_HIGH_MAX,
    RISK_LEVEL_LOW_MAX,
    RISK_LEVEL_MEDIUM_MAX,
    RULE_EXTREME_NEGATIVE_WEIGHT,
    RULE_QUANTITY_SPIKE_WEIGHT,
)
from security.risk_scorer import (
    RULE_EXTREME_NEGATIVE,
    RULE_QUANTITY_SPIKE,
    RULE_REPEATED_REVERSAL,
    RiskScorer,
    _risk_level,
)

FIXTURE = Path(__file__).parent / "fixtures" / "demo_movements.csv"


@pytest.fixture
def demo_movements() -> pd.DataFrame:
    return pd.read_csv(FIXTURE)


def test_risk_level_thresholds() -> None:
    assert _risk_level(0.0) == "LOW"
    assert _risk_level(RISK_LEVEL_LOW_MAX) == "LOW"
    assert _risk_level(RISK_LEVEL_LOW_MAX + 0.01) == "MEDIUM"
    assert _risk_level(RISK_LEVEL_MEDIUM_MAX) == "MEDIUM"
    assert _risk_level(RISK_LEVEL_HIGH_MAX) == "HIGH"
    assert _risk_level(0.9) == "CRITICAL"


def test_quantity_spike_rule_detected(demo_movements: pd.DataFrame) -> None:
    scorer = RiskScorer(demo_movements)
    results = scorer.score_all()
    spike_hits = [r for r in results if r["rule_triggered"] == RULE_QUANTITY_SPIKE]
    assert len(spike_hits) >= 5
    for hit in spike_hits:
        assert any("Quantity spike" in f for f in hit["factors"])
        assert hit["risk_score"] >= RULE_QUANTITY_SPIKE_WEIGHT


def test_extreme_negative_adjustment_detected(demo_movements: pd.DataFrame) -> None:
    scorer = RiskScorer(demo_movements)
    results = scorer.score_all()
    neg_hits = [r for r in results if RULE_EXTREME_NEGATIVE in (r["rule_triggered"],)]
    assert len(neg_hits) >= 5
    for hit in neg_hits:
        assert hit["risk_score"] >= RULE_EXTREME_NEGATIVE_WEIGHT


def test_repeated_reversal_pattern(demo_movements: pd.DataFrame) -> None:
    scorer = RiskScorer(demo_movements)
    part3 = [r for r in scorer.score_all() if r["part_id"] == "PART-003"]
    assert any(RULE_REPEATED_REVERSAL == r["rule_triggered"] for r in part3)


def test_unknown_reference_and_data_quality(demo_movements: pd.DataFrame) -> None:
    scorer = RiskScorer(demo_movements)
    by_id = {r["event_id"]: r for r in scorer.score_all()}
    empty_type = by_id["MOV-000094"]
    unknown_type = by_id["MOV-000095"]
    assert any("Unrecognized or missing reference" in f for f in empty_type["factors"])
    transfer_factors = unknown_type["factors"]
    assert any("Unexpected movement type: transfer" in f for f in transfer_factors)


def test_risk_results_include_factors(demo_movements: pd.DataFrame) -> None:
    scorer = RiskScorer(demo_movements)
    for item in scorer.score_all():
        assert "factors" in item
        assert "risk_score" in item
        assert 0.0 <= item["risk_score"] <= 1.0
