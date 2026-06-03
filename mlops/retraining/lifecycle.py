"""Retraining finalize / failure logic (framework-agnostic, no ZenML import).

Kept separate from :mod:`mlops.retraining.pipeline` so the artifact assembly,
promotion bookkeeping, and safe-failure behaviour are unit-testable without
ZenML installed. The ZenML steps simply call into here.
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Any

from mlops.retraining import core
from mlops.retraining._io import git_commit, write_json
from mlops.retraining.config import RetrainingConfig
from mlops.retraining.gate import STATUS_FAILED
from mlops.retraining.mlflow_run import log_decision
from mlops.retraining.registry_ops import load_champion
from mlops.retraining.summary import build_rollback_manifest, build_summary

logger = logging.getLogger(__name__)


def write_optuna_trials(cfg: RetrainingConfig, tuning: dict[str, Any]) -> Path:
    cfg.artifacts_dir.mkdir(parents=True, exist_ok=True)
    path = cfg.artifacts_dir / "optuna_trials.csv"
    rows = tuning.get("trials", [])
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["trial_number", "params", "value", "state", "duration_seconds"]
        )
        for row in rows:
            writer.writerow(
                [
                    row.get("trial_number"),
                    row.get("params"),
                    row.get("value"),
                    row.get("state"),
                    row.get("duration_seconds"),
                ]
            )
    return path


def maybe_package_bentoml(
    cfg: RetrainingConfig, promoted: bool, warnings: list[str]
) -> dict[str, Any] | None:
    """Reuse the PR-05 BentoML packaging path only after a promotion."""

    if not (cfg.bentoml_enabled and promoted):
        return None
    try:
        from mlops.packaging import package_champion

        result = package_champion(
            tracking_uri=cfg.tracking_uri,
            experiment_name=cfg.experiment_name,
            model_artifact=cfg.model_artifact,
            model_name=cfg.bentoml_model_name,
        )
        return {"status": result.get("status"), "model_tag": result.get("model_tag")}
    except Exception as exc:  # pragma: no cover - packaging is best-effort
        warnings.append(f"BentoML packaging skipped: {type(exc).__name__}: {exc}")
        return {"status": "skipped", "reason": str(exc)}


def finalize_and_write(
    cfg: RetrainingConfig,
    candidate: dict,
    champion: dict,
    gate: dict,
    promotion: dict,
    validation: dict,
    *,
    failure_reason: str | None = None,
) -> dict[str, Any]:
    """Assemble + write all retraining artifacts and log the decision to MLflow."""

    cfg.artifacts_dir.mkdir(parents=True, exist_ok=True)
    comparison = gate.get("comparison", {})
    status = gate.get("status")
    promoted = bool(gate.get("promoted"))
    first_run = bool(gate.get("first_run"))

    if failure_reason is not None:
        status = STATUS_FAILED
        promoted = False

    rejected_reason = (
        gate.get("reason")
        if status == "rejected" and failure_reason is None
        else None
    )

    run_id = candidate.get("run_id")
    champion_metrics = candidate.get("champion_metrics")
    candidate_metrics = candidate.get("metrics", {})

    champion_before = {
        "version": champion.get("version"),
        "run_id": champion.get("run_id"),
        "model_uri": champion.get("model_uri"),
        "source": champion.get("source"),
    }
    if promoted:
        champion_after = {
            "version": promotion.get("candidate_version"),
            "run_id": run_id,
            "alias": cfg.champion_alias,
        }
        rollback_target = promotion.get("previous_champion_version") or champion.get(
            "version"
        )
    else:
        # Rejected/failed: champion is unchanged; the safe target is the current
        # champion (last known good).
        champion_after = champion_before
        rollback_target = champion.get("version") or champion.get("run_id")

    rollback_method = promotion.get("method", "manifest_only")

    warnings: list[str] = list(cfg.warnings)
    warnings.extend(candidate.get("champion_eval_warnings", []))
    warnings.extend(promotion.get("warnings", []))
    if champion.get("source") != "registry_alias" and promoted:
        warnings.append(
            "No pre-existing MLflow champion alias; rollback is recorded via the "
            "manifest. Aliases are established on the next promotion."
        )
    if rollback_target is None:
        warnings.append(
            "No previous champion to roll back to (first promotion); rollback "
            "target is null until a second promotion occurs."
        )

    bentoml_artifact = maybe_package_bentoml(cfg, promoted, warnings)

    summary = build_summary(
        run_id=run_id,
        git_commit=git_commit(),
        mode=cfg.mode,
        model_name=cfg.registered_model_name,
        primary_metric=cfg.primary_metric,
        metric_direction=cfg.metric_direction,
        comparison=comparison,
        status=status,
        promoted=promoted,
        first_run=first_run,
        rejected_reason=rejected_reason,
        failure_reason=failure_reason,
        rollback_target=rollback_target,
        data_reference=candidate.get("data_reference"),
        config_reference=cfg.as_reference(),
        bentoml_artifact=bentoml_artifact,
        secondary_metrics={
            k: v for k, v in candidate_metrics.items() if k != cfg.primary_metric
        },
        cost_context=candidate.get("cost_context"),
        tuning=candidate.get("tuning", {"enabled": False}),
        package_versions=core.package_versions(),
        champion_before=champion_before,
        champion_after=champion_after,
        warnings=warnings,
    )

    rollback_manifest = build_rollback_manifest(
        champion_before=champion_before,
        champion_after=champion_after,
        candidate_run_id=run_id,
        rollback_target=rollback_target,
        rollback_method=rollback_method,
        metrics_before=champion_metrics or {},
        metrics_after=candidate_metrics,
        previous_champion=champion_before,
        promoted_model=champion_after if promoted else None,
        notes=[
            "Generated by the PR-09 retraining pipeline.",
            "No model versions are ever deleted. Use `make model-rollback` "
            "(dry-run by default) to inspect/execute rollback.",
        ],
    )

    summary_path = write_json(cfg.artifacts_dir / "retraining_summary.json", summary)
    rollback_path = write_json(
        cfg.artifacts_dir / "rollback_manifest.json", rollback_manifest
    )
    write_json(
        cfg.artifacts_dir / "latest_candidate_metrics.json",
        {
            "primary_metric": cfg.primary_metric,
            "metrics": candidate_metrics,
            "run_id": run_id,
            "tuning_enabled": candidate.get("tuning", {}).get("enabled", False),
        },
    )
    write_json(cfg.artifacts_dir / "latest_comparison.json", comparison)
    if candidate.get("error_analysis"):
        write_json(
            cfg.artifacts_dir / "error_analysis.json", candidate["error_analysis"]
        )

    log_decision(
        cfg,
        run_id,
        status=status,
        promoted=promoted,
        comparison=comparison,
        promotion=promotion,
        summary_path=summary_path,
        rollback_path=rollback_path,
    )

    summary["artifacts"] = {
        "retraining_summary": str(summary_path),
        "rollback_manifest": str(rollback_path),
        "latest_candidate_metrics": str(
            cfg.artifacts_dir / "latest_candidate_metrics.json"
        ),
        "latest_comparison": str(cfg.artifacts_dir / "latest_comparison.json"),
        "optuna_trials": candidate.get("optuna_trials_path"),
        "error_analysis": str(cfg.artifacts_dir / "error_analysis.json")
        if candidate.get("error_analysis")
        else None,
    }
    return summary


def write_failed_summary(cfg: RetrainingConfig, reason: str) -> dict[str, Any]:
    """Write a failed summary that preserves the last known safe champion."""

    champion = load_champion(
        tracking_uri=cfg.tracking_uri,
        model_name=cfg.registered_model_name,
        champion_alias=cfg.champion_alias,
        forecast_experiment=cfg.forecast_experiment,
        model_artifact=cfg.model_artifact,
    )
    gate = {
        "status": STATUS_FAILED,
        "promoted": False,
        "first_run": not champion.get("available"),
        "comparison": {
            "candidate_metric": None,
            "champion_metric": None,
            "metric_direction": cfg.metric_direction,
            "absolute_delta": None,
            "relative_delta_pct": None,
            "promotion_threshold": cfg.promotion_threshold_pct,
            "promoted": False,
        },
    }
    candidate: dict[str, Any] = {
        "run_id": None,
        "metrics": {},
        "tuning": {"enabled": False},
        "data_reference": None,
        "champion_metrics": champion.get("logged_metrics") or None,
    }
    promotion = {"method": "manifest_only", "registered": False}
    return finalize_and_write(
        cfg,
        candidate,
        champion,
        gate,
        promotion,
        {"passed": False},
        failure_reason=reason,
    )
