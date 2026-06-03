"""Conservative champion/challenger promotion gate for retraining.

The gate is a pure function so it is fully unit-testable without ZenML, MLflow,
or training. It reuses :func:`mlops.comparison.compare_models` for the
direction-aware delta math, so the retraining promotion rule stays consistent
with the PR-05 champion/challenger comparison and respects ``metric_direction``
(``lower_is_better`` vs ``higher_is_better``) rather than any hardcoded "<".

Decision contract (AA-6):

* ``promoted``      -- candidate beats champion by >= threshold (gates passed).
* ``first_run_promoted`` -- no champion exists yet and candidate metrics are
  valid.
* ``rejected``      -- candidate not better than champion by threshold, or
  validation failed, or metrics are missing/non-finite.
* ``failed``        -- handled by the caller when training/eval raises; never
  produced here.

"Pipeline completed without error" is NOT sufficient: the gate requires the
primary metric to exist and be a finite number.
"""

from __future__ import annotations

from typing import Any

from mlops.comparison import DECISION_PROMOTE, compare_models

from mlops.retraining._io import is_finite_number

STATUS_PROMOTED = "promoted"
STATUS_FIRST_RUN_PROMOTED = "first_run_promoted"
STATUS_REJECTED = "rejected"
STATUS_FAILED = "failed"


def _empty_comparison(
    candidate_metric: Any,
    champion_metric: Any,
    *,
    metric_direction: str,
    promotion_threshold_pct: float,
) -> dict[str, Any]:
    return {
        "candidate_metric": candidate_metric if is_finite_number(candidate_metric)
        else None,
        "champion_metric": champion_metric if is_finite_number(champion_metric)
        else None,
        "metric_direction": metric_direction,
        "absolute_delta": None,
        "relative_delta_pct": None,
        "promotion_threshold": float(promotion_threshold_pct),
        "promoted": False,
    }


def evaluate_promotion_gate(
    *,
    candidate_metrics: dict[str, Any],
    champion_metrics: dict[str, Any] | None,
    primary_metric: str,
    metric_direction: str = "lower_is_better",
    promotion_threshold_pct: float = 5.0,
    validation_passed: bool = True,
) -> dict[str, Any]:
    """Decide whether the candidate may be promoted over the champion.

    Returns a stable dict with ``status``, ``promoted``, ``reason`` and a
    ``comparison`` block (candidate_metric, champion_metric, metric_direction,
    absolute_delta, relative_delta_pct, promotion_threshold, promoted).
    """

    candidate_value = candidate_metrics.get(primary_metric)
    champion_value = (
        None if champion_metrics is None else champion_metrics.get(primary_metric)
    )
    comparison = _empty_comparison(
        candidate_value,
        champion_value,
        metric_direction=metric_direction,
        promotion_threshold_pct=promotion_threshold_pct,
    )

    # Hard prerequisites first.
    if not validation_passed:
        return {
            "status": STATUS_REJECTED,
            "promoted": False,
            "first_run": champion_metrics is None,
            "reason": "Data/artifact validation failed; candidate not promoted.",
            "comparison": comparison,
        }

    if not is_finite_number(candidate_value):
        return {
            "status": STATUS_REJECTED,
            "promoted": False,
            "first_run": champion_metrics is None,
            "reason": (
                f"Candidate primary metric '{primary_metric}' is missing or "
                "non-finite; candidate not promoted."
            ),
            "comparison": comparison,
        }

    # First-run: no champion exists yet. Promote only because metrics are valid.
    if champion_metrics is None or not is_finite_number(champion_value):
        return {
            "status": STATUS_FIRST_RUN_PROMOTED,
            "promoted": True,
            "first_run": True,
            "reason": (
                "No existing champion; candidate metrics are valid, so the first "
                "candidate is promoted to bootstrap the champion."
            ),
            "comparison": {**comparison, "promoted": True},
        }

    # Direction-aware comparison: candidate plays the challenger role.
    result = compare_models(
        champion_metrics,
        candidate_metrics,
        primary_metric=primary_metric,
        primary_metric_direction=metric_direction,
        decision_threshold_pct=promotion_threshold_pct,
    )
    delta_block = result["comparison"]
    promoted = result["decision"] == DECISION_PROMOTE
    comparison.update(
        {
            "absolute_delta": delta_block.get("absolute_delta"),
            "relative_delta_pct": delta_block.get("relative_improvement_pct"),
            "promoted": promoted,
        }
    )

    return {
        "status": STATUS_PROMOTED if promoted else STATUS_REJECTED,
        "promoted": promoted,
        "first_run": False,
        "reason": result["reason"],
        "comparison": comparison,
    }
