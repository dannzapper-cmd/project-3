"""Champion/challenger comparison from existing PR-03/PR-04 artifacts.

Strict rules (per PR-05 spec):

* Uses ONLY metric values that already exist in PR-03 (MLflow run metrics) and
  PR-04 (``decision_summary.json``) artifacts. Nothing is recomputed from raw
  data, no training or backtesting is re-run, and no existing metric file is
  mutated.
* Both models share the same PR-03 temporal split, so the comparison is
  apples-to-apples on the stated primary metric.
* The decision is one of ``promote_challenger``, ``keep_champion`` or
  ``manual_review``. When metrics are too close (relative improvement below the
  configured threshold) or incomplete, the decision is ``manual_review`` rather
  than a forced winner.
* Synthetic cost figures are labelled synthetic/simulated and never presented
  as real-world savings.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

DECISION_PROMOTE = "promote_challenger"
DECISION_KEEP = "keep_champion"
DECISION_MANUAL = "manual_review"

WARNINGS = [
    "Comparison uses synthetic-data metrics only; not a real-world performance "
    "claim.",
    "Champion/challenger metrics are read from existing PR-03/PR-04 artifacts "
    "and are never recomputed here.",
]


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not (
        isinstance(value, float) and math.isnan(value)
    )


def compare_models(
    champion: dict[str, Any],
    challenger: dict[str, Any],
    *,
    primary_metric: str,
    primary_metric_direction: str = "lower_is_better",
    decision_threshold_pct: float = 5.0,
) -> dict[str, Any]:
    """Compare two models on a primary metric and return a decision dict.

    ``champion`` / ``challenger`` are dicts of metric_name -> value (e.g.
    ``{"mae": 2.1, "rmse": 3.1, "mape": 26.4}``).
    """

    if primary_metric_direction not in {"lower_is_better", "higher_is_better"}:
        raise ValueError(
            "primary_metric_direction must be 'lower_is_better' or "
            "'higher_is_better'"
        )

    champ_val = champion.get(primary_metric)
    chal_val = challenger.get(primary_metric)
    warnings_list: list[str] = []

    comparison: dict[str, Any] = {
        "primary_metric_champion": champ_val if _is_number(champ_val) else None,
        "primary_metric_challenger": chal_val if _is_number(chal_val) else None,
        "absolute_delta": None,
        "relative_improvement_pct": None,
        "decision_threshold_pct": float(decision_threshold_pct),
    }

    if not _is_number(champ_val) or not _is_number(chal_val):
        warnings_list.append(
            f"Primary metric '{primary_metric}' is missing or non-numeric for "
            "champion and/or challenger; cannot compute a winner."
        )
        return {
            "comparison": comparison,
            "decision": DECISION_MANUAL,
            "reason": (
                "Incomplete metrics: primary metric unavailable for one or both "
                "models. Manual review required."
            ),
            "warnings": warnings_list,
        }

    champ_val = float(champ_val)
    chal_val = float(chal_val)
    absolute_delta = chal_val - champ_val

    if champ_val == 0:
        warnings_list.append(
            "Champion primary metric is zero; relative improvement is undefined."
        )
        return {
            "comparison": {**comparison, "absolute_delta": absolute_delta},
            "decision": DECISION_MANUAL,
            "reason": (
                "Champion primary metric is zero; relative improvement cannot be "
                "computed. Manual review required."
            ),
            "warnings": warnings_list,
        }

    # Positive => challenger is better than champion.
    if primary_metric_direction == "lower_is_better":
        relative_improvement_pct = (champ_val - chal_val) / abs(champ_val) * 100.0
    else:
        relative_improvement_pct = (chal_val - champ_val) / abs(champ_val) * 100.0

    comparison["absolute_delta"] = absolute_delta
    comparison["relative_improvement_pct"] = relative_improvement_pct

    threshold = float(decision_threshold_pct)
    if abs(relative_improvement_pct) < threshold:
        decision = DECISION_MANUAL
        reason = (
            f"Models are within {threshold:.1f}% on {primary_metric} "
            f"(relative improvement {relative_improvement_pct:+.2f}%). "
            "Too close to call; manual review required."
        )
    elif relative_improvement_pct >= threshold:
        decision = DECISION_PROMOTE
        reason = (
            f"Challenger improves {primary_metric} by "
            f"{relative_improvement_pct:.2f}% (>= {threshold:.1f}% threshold)."
        )
    else:
        decision = DECISION_KEEP
        reason = (
            f"Champion is better on {primary_metric} by "
            f"{abs(relative_improvement_pct):.2f}% (>= {threshold:.1f}% "
            "threshold)."
        )

    return {
        "comparison": comparison,
        "decision": decision,
        "reason": reason,
        "warnings": warnings_list,
    }


def extract_model_metrics(
    run_metrics: dict[str, float],
    model_name: str,
    *,
    metric_names: tuple[str, ...] = ("mae", "rmse", "mape"),
) -> dict[str, float | None]:
    """Extract ``<model_name>_<metric>`` values from a flat MLflow metric dict."""

    extracted: dict[str, float | None] = {}
    for metric in metric_names:
        key = f"{model_name}_{metric}"
        value = run_metrics.get(key)
        extracted[metric] = float(value) if _is_number(value) else None
    return extracted


def load_pr03_run(
    tracking_uri: str,
    experiment_name: str,
) -> dict[str, Any] | None:
    """Load the latest finished PR-03 run's metrics from MLflow (read-only).

    Returns ``None`` if the experiment or a usable run cannot be found.
    """

    import mlflow
    from mlflow.tracking import MlflowClient

    mlflow.set_tracking_uri(tracking_uri)
    client = MlflowClient(tracking_uri=tracking_uri)
    experiment = client.get_experiment_by_name(experiment_name)
    if experiment is None:
        return None

    runs = client.search_runs(
        [experiment.experiment_id],
        order_by=["attributes.start_time DESC"],
        max_results=1,
    )
    if not runs:
        return None

    run = runs[0]
    return {
        "run_id": run.info.run_id,
        "metrics": dict(run.data.metrics),
        "params": dict(run.data.params),
    }


def load_pr04_context(summary_path: Path) -> dict[str, Any]:
    """Read PR-04 decision-intelligence summary (read-only) for context.

    Never mutates the file. Returns a labelled, synthetic supporting-context
    block plus any gaps as warnings.
    """

    if not summary_path.exists():
        return {
            "available": False,
            "warnings": [
                f"PR-04 decision summary not found at {summary_path}; cost "
                "context omitted."
            ],
        }

    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return {
            "available": False,
            "warnings": [f"Could not read PR-04 decision summary: {exc}"],
        }

    cost_metrics = summary.get("cost_metrics", {})
    context = {
        "available": True,
        "source": str(summary_path),
        "synthetic": True,
        "label": "synthetic/simulated decision-layer cost diagnostics",
        "test_period": summary.get("test_period"),
        "selected_pinball_loss": cost_metrics.get("selected_pinball_loss"),
        "cost_reduction_vs_best_baseline_pct": cost_metrics.get(
            "cost_reduction_vs_best_baseline_pct"
        ),
        "warnings": [
            "PR-04 cost reductions are synthetic/simulated and are not "
            "real-world savings.",
        ],
    }
    if cost_metrics.get("selected_pinball_loss") is None:
        context["warnings"].append(
            "PR-04 cost metric (pinball loss) missing; cost context incomplete."
        )
    return context
