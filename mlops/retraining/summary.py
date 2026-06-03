"""Stable, documented artifact schemas for retraining.

These schemas are a contract for downstream QA / dashboard consumption, so the
field sets are fixed and validated. Key rule (per the surgical correction): on
failed runs, first-run cases, or when a metric/champion/candidate does not
exist, the required fields are still PRESENT but set to ``null`` -- never a fake
``0.0``.
"""

from __future__ import annotations

from typing import Any

from mlops.retraining import (
    ERROR_ANALYSIS_SCHEMA_VERSION,
    ROLLBACK_SCHEMA_VERSION,
    SUMMARY_SCHEMA_VERSION,
)
from mlops.retraining._io import now_utc

# Required top-level keys for retraining_summary.json (AA-7).
SUMMARY_REQUIRED_FIELDS: tuple[str, ...] = (
    "schema_version",
    "run_id",
    "timestamp",
    "git_commit",
    "pipeline_mode",
    "model_name",
    "primary_metric",
    "metric_direction",
    "candidate_metric",
    "champion_metric",
    "absolute_delta",
    "relative_delta_pct",
    "promotion_threshold",
    "status",
    "promoted",
    "rejected_reason",
    "failure_reason",
    "first_run",
    "rollback_target",
    "data_reference",
    "config_reference",
    "bentoml_artifact",
    "warnings",
)

# Required keys for rollback_manifest.json (AA-7).
ROLLBACK_REQUIRED_FIELDS: tuple[str, ...] = (
    "schema_version",
    "timestamp",
    "champion_before",
    "champion_after",
    "candidate_run_id",
    "rollback_target",
    "rollback_method",
    "metrics_before",
    "metrics_after",
    "dry_run_available",
)


def build_summary(
    *,
    run_id: str | None,
    git_commit: str | None,
    mode: str,
    model_name: str,
    primary_metric: str,
    metric_direction: str,
    comparison: dict[str, Any],
    status: str,
    promoted: bool,
    first_run: bool,
    rejected_reason: str | None,
    failure_reason: str | None,
    rollback_target: Any,
    data_reference: Any,
    config_reference: dict[str, Any],
    bentoml_artifact: Any,
    secondary_metrics: dict[str, Any] | None = None,
    cost_context: dict[str, Any] | None = None,
    statistical_significance: dict[str, Any] | None = None,
    tuning: dict[str, Any] | None = None,
    package_versions: dict[str, Any] | None = None,
    champion_before: Any = None,
    champion_after: Any = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    """Assemble a schema-stable retraining summary.

    All required fields are always present; uncomputed numeric fields are
    ``None`` (never a placeholder ``0.0``).
    """

    summary: dict[str, Any] = {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "run_id": run_id,
        "timestamp": now_utc(),
        "git_commit": git_commit,
        "pipeline_mode": mode,
        "model_name": model_name,
        "primary_metric": primary_metric,
        "metric_direction": metric_direction,
        "candidate_metric": comparison.get("candidate_metric"),
        "champion_metric": comparison.get("champion_metric"),
        "absolute_delta": comparison.get("absolute_delta"),
        "relative_delta_pct": comparison.get("relative_delta_pct"),
        "promotion_threshold": comparison.get("promotion_threshold"),
        "status": status,
        "promoted": bool(promoted),
        "rejected_reason": rejected_reason,
        "failure_reason": failure_reason,
        "first_run": bool(first_run),
        "rollback_target": rollback_target,
        "data_reference": data_reference,
        "config_reference": config_reference,
        "bentoml_artifact": bentoml_artifact,
        # Context-only blocks (secondary; never gate promotion).
        "champion_before": champion_before,
        "champion_after": champion_after,
        "secondary_metrics": secondary_metrics or {},
        "cost_context": cost_context
        or {"cost_metric_available": False},
        "statistical_significance": statistical_significance
        or {
            "available": False,
            "note": (
                "Statistical significance testing requires repeated forecast "
                "errors/backtest windows and is deferred until richer "
                "backtesting artifacts are available."
            ),
        },
        "tuning": tuning or {"enabled": False},
        "package_versions": package_versions or {},
        "warnings": sorted(set(warnings or [])),
    }
    return summary


def build_rollback_manifest(
    *,
    champion_before: Any,
    champion_after: Any,
    candidate_run_id: str | None,
    rollback_target: Any,
    rollback_method: str,
    metrics_before: dict[str, Any] | None,
    metrics_after: dict[str, Any] | None,
    previous_champion: Any = None,
    promoted_model: Any = None,
    history: list[dict[str, Any]] | None = None,
    notes: list[str] | None = None,
) -> dict[str, Any]:
    """Assemble a schema-stable rollback manifest.

    ``rollback_method`` is one of ``mlflow_alias`` or ``manifest_only``.
    """

    return {
        "schema_version": ROLLBACK_SCHEMA_VERSION,
        "timestamp": now_utc(),
        "champion_before": champion_before,
        "champion_after": champion_after,
        "previous_champion": previous_champion,
        "promoted_model": promoted_model,
        "candidate_run_id": candidate_run_id,
        "rollback_target": rollback_target,
        "rollback_method": rollback_method,
        "metrics_before": metrics_before or {},
        "metrics_after": metrics_after or {},
        "dry_run_available": True,
        "history": history or [],
        "notes": notes or [],
    }


def build_error_analysis(
    *,
    available: bool,
    worst_items_by_error: list[dict[str, Any]] | None = None,
    intermittent_demand_items_error: dict[str, Any] | None = None,
    high_stockout_risk_items_error: dict[str, Any] | None = None,
    notes: list[str] | None = None,
) -> dict[str, Any]:
    """Assemble the optional error-analysis artifact."""

    return {
        "schema_version": ERROR_ANALYSIS_SCHEMA_VERSION,
        "timestamp": now_utc(),
        "available": available,
        "worst_items_by_error": worst_items_by_error or [],
        "intermittent_demand_items_error": intermittent_demand_items_error,
        "high_stockout_risk_items_error": high_stockout_risk_items_error,
        "notes": notes or [],
    }


def validate_required_fields(
    payload: dict[str, Any], required: tuple[str, ...]
) -> list[str]:
    """Return a list of missing required keys (empty when valid)."""

    return [field for field in required if field not in payload]
