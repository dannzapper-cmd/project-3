"""Behavioral tests for the PR-09 promotion gate.

These verify behaviour, not imports. The gate must respect ``metric_direction``
(``lower_is_better`` vs ``higher_is_better``) rather than any hardcoded "<".
"""

from __future__ import annotations

import math

import pytest

from mlops.retraining.gate import (
    STATUS_FIRST_RUN_PROMOTED,
    STATUS_PROMOTED,
    STATUS_REJECTED,
    evaluate_promotion_gate,
)

THRESHOLD = 5.0


def _gate(candidate, champion, direction, *, validation=True):
    return evaluate_promotion_gate(
        candidate_metrics={"metric": candidate} if candidate is not None else {},
        champion_metrics=None if champion is None else {"metric": champion},
        primary_metric="metric",
        metric_direction=direction,
        promotion_threshold_pct=THRESHOLD,
        validation_passed=validation,
    )


# --- lower_is_better -------------------------------------------------------

def test_lower_is_better_promotes_when_candidate_clearly_lower():
    # 2.0 -> 1.5 is a 25% improvement (> 5% threshold).
    result = _gate(1.5, 2.0, "lower_is_better")
    assert result["promoted"] is True
    assert result["status"] == STATUS_PROMOTED
    assert result["comparison"]["relative_delta_pct"] > THRESHOLD


def test_lower_is_better_rejects_when_candidate_higher():
    # Candidate worse (higher mae) -> reject, champion untouched.
    result = _gate(2.5, 2.0, "lower_is_better")
    assert result["promoted"] is False
    assert result["status"] == STATUS_REJECTED


def test_lower_is_better_rejects_when_within_threshold():
    # 2.0 -> 1.98 is only 1% improvement (< 5%): too close to call.
    result = _gate(1.98, 2.0, "lower_is_better")
    assert result["promoted"] is False
    assert result["status"] == STATUS_REJECTED


# --- higher_is_better ------------------------------------------------------

def test_higher_is_better_promotes_when_candidate_clearly_higher():
    # 0.50 -> 0.80 is a 60% improvement upward.
    result = _gate(0.80, 0.50, "higher_is_better")
    assert result["promoted"] is True
    assert result["status"] == STATUS_PROMOTED


def test_higher_is_better_rejects_when_candidate_lower():
    # For higher_is_better, a LOWER candidate is worse and must be rejected even
    # though candidate_metric < champion_metric.
    result = _gate(0.40, 0.50, "higher_is_better")
    assert result["promoted"] is False
    assert result["status"] == STATUS_REJECTED


def test_direction_flips_the_decision_for_same_values():
    lower = _gate(1.5, 2.0, "lower_is_better")
    higher = _gate(1.5, 2.0, "higher_is_better")
    # Same raw values, opposite verdicts depending on direction.
    assert lower["promoted"] is True
    assert higher["promoted"] is False


# --- first run / validation / invalid metrics ------------------------------

def test_first_run_promotes_with_valid_metric():
    result = _gate(1.5, None, "lower_is_better")
    assert result["status"] == STATUS_FIRST_RUN_PROMOTED
    assert result["promoted"] is True
    assert result["first_run"] is True


def test_first_run_rejected_when_metric_not_finite():
    result = _gate(math.nan, None, "lower_is_better")
    assert result["promoted"] is False
    assert result["status"] == STATUS_REJECTED


def test_validation_failure_blocks_promotion():
    result = _gate(1.0, 2.0, "lower_is_better", validation=False)
    assert result["promoted"] is False
    assert result["status"] == STATUS_REJECTED


def test_missing_candidate_metric_is_rejected():
    result = _gate(None, 2.0, "lower_is_better")
    assert result["promoted"] is False
    assert result["status"] == STATUS_REJECTED


def test_comparison_block_uses_null_when_uncomputed():
    # Rejected-by-validation: deltas were never computed, so they must be null
    # (not a fake 0.0).
    result = _gate(1.0, 2.0, "lower_is_better", validation=False)
    comparison = result["comparison"]
    assert comparison["absolute_delta"] is None
    assert comparison["relative_delta_pct"] is None
    assert comparison["promotion_threshold"] == THRESHOLD


def test_invalid_direction_raises():
    with pytest.raises(ValueError):
        evaluate_promotion_gate(
            candidate_metrics={"metric": 1.0},
            champion_metrics={"metric": 2.0},
            primary_metric="metric",
            metric_direction="sideways",
            promotion_threshold_pct=THRESHOLD,
        )
