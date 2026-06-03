"""ZenML retraining pipeline (LOCAL DAG runner only).

ZenML is used here purely as a *local* DAG runner with typed steps and local
pipeline metadata (default SQLite stack). There is no remote stack, no ZenML
cloud, and no scheduler. Heavy objects (the trained model, the test frame) stay
local to the step that produces them; only JSON-serializable summaries flow
between steps, with MLflow acting as the heavy-artifact store.

The config is threaded through as a plain-dict step parameter (ZenML runs steps
in isolated contexts, so module globals are not reliable). The actual work lives
in :mod:`mlops.retraining.core` and :mod:`mlops.retraining.lifecycle`; these
steps are thin wrappers.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
from zenml import pipeline, step

from ml.train import load_config
from mlops.retraining import core, lifecycle
from mlops.retraining._io import read_json
from mlops.retraining.config import RetrainingConfig
from mlops.retraining.gate import evaluate_promotion_gate
from mlops.retraining.mlflow_run import log_candidate_run
from mlops.retraining.registry_ops import load_champion, promote_candidate

# Re-export so existing call sites / tests can import from either module.
finalize_and_write = lifecycle.finalize_and_write

logger = logging.getLogger(__name__)


@step(enable_cache=False)
def load_training_data_step(cfg_dict: dict) -> pd.DataFrame:
    return core.load_training_data(RetrainingConfig.from_dict(cfg_dict))


@step(enable_cache=False)
def verify_artifacts_step(featured: pd.DataFrame) -> dict:
    return core.verify_artifacts(featured)


@step(enable_cache=False)
def load_current_champion_step(cfg_dict: dict) -> dict:
    cfg = RetrainingConfig.from_dict(cfg_dict)
    return load_champion(
        tracking_uri=cfg.tracking_uri,
        model_name=cfg.registered_model_name,
        champion_alias=cfg.champion_alias,
        forecast_experiment=cfg.forecast_experiment,
        model_artifact=cfg.model_artifact,
    )


@step(enable_cache=False)
def train_and_evaluate_candidate_step(
    cfg_dict: dict,
    featured: pd.DataFrame,
    validation: dict,
    champion: dict,
) -> dict:
    """Train (optionally tune), evaluate candidate + champion on the SAME split."""

    cfg = RetrainingConfig.from_dict(cfg_dict)
    if not validation.get("passed"):
        return {"trained": False, "metrics": {}, "tuning": {"enabled": False}}

    ml_config = load_config(cfg.ml_config_path)
    candidate = core.train_candidate(cfg, featured, ml_config)
    test_df = candidate.pop("_test_df")
    preds = candidate.pop("_preds")
    model = candidate.pop("_model")

    champion_eval = core.evaluate_champion_on_test(
        cfg, champion, test_df, candidate["feature_list"]
    )
    error_analysis = core.build_error_analysis_payload(cfg, test_df, preds)

    optuna_trials_path: Path | None = None
    if candidate["tuning"].get("enabled"):
        optuna_trials_path = lifecycle.write_optuna_trials(cfg, candidate["tuning"])

    candidate["_model"] = model  # re-attach for logging
    run_id = log_candidate_run(
        cfg, candidate, core.data_reference(cfg, featured), optuna_trials_path
    )
    candidate.pop("_model", None)

    return {
        "trained": True,
        "run_id": run_id,
        "metrics": candidate["metrics"],
        "params": candidate["params"],
        "feature_list": candidate["feature_list"],
        "tuning": candidate["tuning"],
        "train_period": candidate["train_period"],
        "test_period": candidate["test_period"],
        "train_rows": candidate["train_rows"],
        "test_rows": candidate["test_rows"],
        "data_reference": core.data_reference(cfg, featured),
        "champion_metrics": champion_eval["metrics"],
        "champion_evaluation": champion_eval["evaluation"],
        "champion_eval_warnings": champion_eval["warnings"],
        "error_analysis": error_analysis,
        "cost_context": core.load_cost_context(cfg),
        "optuna_trials_path": str(optuna_trials_path) if optuna_trials_path else None,
    }


@step(enable_cache=False)
def compare_candidate_to_champion_step(
    cfg_dict: dict,
    candidate: dict,
    validation: dict,
) -> dict:
    cfg = RetrainingConfig.from_dict(cfg_dict)
    return evaluate_promotion_gate(
        candidate_metrics=candidate.get("metrics", {}),
        champion_metrics=candidate.get("champion_metrics"),
        primary_metric=cfg.primary_metric,
        metric_direction=cfg.metric_direction,
        promotion_threshold_pct=cfg.promotion_threshold_pct,
        validation_passed=bool(validation.get("passed")),
    )


@step(enable_cache=False)
def promote_or_reject_step(
    cfg_dict: dict,
    candidate: dict,
    champion: dict,
    gate: dict,
) -> dict:
    """Promote via controlled MLflow alias mutation only when the gate passes."""

    cfg = RetrainingConfig.from_dict(cfg_dict)
    promotion: dict = {
        "method": "mlflow_alias"
        if champion.get("source") == "registry_alias"
        else "manifest_only",
        "registered": False,
        "candidate_version": None,
        "previous_champion_version": champion.get("version"),
    }

    run_id = candidate.get("run_id")
    if gate.get("promoted") and run_id:
        promotion = promote_candidate(
            tracking_uri=cfg.tracking_uri,
            model_name=cfg.registered_model_name,
            candidate_run_id=run_id,
            model_artifact=cfg.model_artifact,
            champion_alias=cfg.champion_alias,
            previous_champion_alias=cfg.previous_champion_alias,
            candidate_tag=cfg.candidate_tag,
        )
    return promotion


@step(enable_cache=False)
def write_retraining_summary_step(
    cfg_dict: dict,
    candidate: dict,
    champion: dict,
    gate: dict,
    promotion: dict,
    validation: dict,
) -> dict:
    cfg = RetrainingConfig.from_dict(cfg_dict)
    return lifecycle.finalize_and_write(
        cfg, candidate, champion, gate, promotion, validation
    )


@pipeline(enable_cache=False)
def retraining_pipeline(cfg_dict: dict) -> None:
    featured = load_training_data_step(cfg_dict)
    validation = verify_artifacts_step(featured)
    champion = load_current_champion_step(cfg_dict)
    candidate = train_and_evaluate_candidate_step(
        cfg_dict, featured, validation, champion
    )
    gate = compare_candidate_to_champion_step(cfg_dict, candidate, validation)
    promotion = promote_or_reject_step(cfg_dict, candidate, champion, gate)
    write_retraining_summary_step(
        cfg_dict, candidate, champion, gate, promotion, validation
    )


def run_retraining(cfg: RetrainingConfig) -> dict:
    """Run the ZenML retraining pipeline and return the summary.

    On an unexpected failure, a schema-stable ``failed`` summary + rollback
    manifest are still written so the current champion is never left in a
    half-promoted state.
    """

    cfg.artifacts_dir.mkdir(parents=True, exist_ok=True)
    try:
        retraining_pipeline(cfg.to_dict())
    except Exception as exc:
        logger.exception("Retraining pipeline failed: %s", exc)
        return lifecycle.write_failed_summary(cfg, f"{type(exc).__name__}: {exc}")

    summary_path = cfg.artifacts_dir / "retraining_summary.json"
    if summary_path.exists():
        return read_json(summary_path)
    return lifecycle.write_failed_summary(
        cfg, "Pipeline completed without writing a summary."
    )
