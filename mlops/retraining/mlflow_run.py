"""MLflow tracking for retraining runs (create candidate run, log decision).

A single retraining run is created for the candidate (params, metrics, model,
tuning artifacts). The promotion/rollback decision is appended to the SAME run
id afterwards. No runs, versions, or experiments are ever deleted.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from mlops.retraining.config import RetrainingConfig

logger = logging.getLogger(__name__)


def _ensure_tracking(cfg: RetrainingConfig) -> Any:
    import mlflow

    os.environ.setdefault("MLFLOW_ALLOW_FILE_STORE", "true")
    mlflow.set_tracking_uri(cfg.tracking_uri)
    mlflow.set_experiment(cfg.experiment_name)
    return mlflow


def log_candidate_run(
    cfg: RetrainingConfig,
    candidate: dict[str, Any],
    data_ref: dict[str, Any],
    optuna_trials_path: Path | None,
) -> str | None:
    """Create the retraining MLflow run; log candidate params/metrics/model."""

    try:
        mlflow = _ensure_tracking(cfg)
    except Exception as exc:  # pragma: no cover - mlflow import/connection guard
        logger.warning("MLflow tracking unavailable: %s", exc)
        return None

    try:
        with mlflow.start_run(run_name=f"retrain_{cfg.mode}") as run:
            run_id = run.info.run_id
            mlflow.set_tags(
                {
                    "scope": "pr09",
                    "pipeline": cfg.pipeline_name,
                    "mode": cfg.mode,
                    "data_source": "synthetic",
                    "production_ready": "false",
                }
            )
            mlflow.log_params(
                {
                    "mode": cfg.mode,
                    "random_seed": cfg.random_seed,
                    "primary_metric": cfg.primary_metric,
                    "metric_direction": cfg.metric_direction,
                    "promotion_threshold_pct": cfg.promotion_threshold_pct,
                    "tune": cfg.tune,
                    "optuna_trials": cfg.optuna_trials,
                    "train_period": candidate.get("train_period"),
                    "test_period": candidate.get("test_period"),
                    "num_items": data_ref.get("num_items"),
                }
            )
            for key, value in candidate.get("params", {}).items():
                mlflow.log_param(f"lgbm_{key}", value)
            for name, value in candidate.get("metrics", {}).items():
                mlflow.log_metric(f"candidate_{name}", float(value))

            tuning = candidate.get("tuning", {})
            if tuning.get("enabled"):
                mlflow.log_metric(
                    "optuna_best_value", float(tuning.get("best_value"))
                )
                mlflow.log_param("optuna_n_trials", tuning.get("n_trials_completed"))
                if optuna_trials_path and optuna_trials_path.exists():
                    mlflow.log_artifact(str(optuna_trials_path), "retraining")

            model = candidate.get("_model")
            if model is not None:
                try:
                    mlflow.lightgbm.log_model(
                        model, artifact_path=cfg.model_artifact
                    )
                except Exception as exc:
                    logger.warning("Could not log candidate model: %s", exc)
            return run_id
    except Exception as exc:
        logger.warning("Failed to create candidate MLflow run: %s", exc)
        return None


def log_decision(
    cfg: RetrainingConfig,
    run_id: str | None,
    *,
    status: str,
    promoted: bool,
    comparison: dict[str, Any],
    promotion: dict[str, Any],
    summary_path: Path | None,
    rollback_path: Path | None,
) -> None:
    """Append the promotion/rollback decision to the candidate run."""

    if run_id is None:
        return
    try:
        mlflow = _ensure_tracking(cfg)
        with mlflow.start_run(run_id=run_id):
            mlflow.set_tags(
                {
                    "retraining_status": status,
                    "promoted": str(bool(promoted)).lower(),
                }
            )
            if comparison.get("champion_metric") is not None:
                mlflow.log_metric(
                    "champion_metric", float(comparison["champion_metric"])
                )
            if comparison.get("relative_delta_pct") is not None:
                mlflow.log_metric(
                    "relative_delta_pct", float(comparison["relative_delta_pct"])
                )
            if promotion.get("candidate_version") is not None:
                mlflow.log_param(
                    "promoted_model_version", promotion["candidate_version"]
                )
            mlflow.log_param("rollback_method", promotion.get("method"))
            for label, path in (
                ("retraining", summary_path),
                ("retraining", rollback_path),
            ):
                if path and Path(path).exists():
                    mlflow.log_artifact(str(path), label)
    except Exception as exc:  # pragma: no cover - logging best effort
        logger.warning("Could not log retraining decision to MLflow: %s", exc)
