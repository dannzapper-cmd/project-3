"""Core retraining step logic (framework-agnostic).

These functions contain the actual work and are independently unit-testable.
The ZenML pipeline in :mod:`mlops.retraining.pipeline` wires them into a typed
DAG; the same functions could be called directly. Nothing here is cloud,
Kubernetes, or scheduled.

MLflow is used as the heavy-artifact store: the candidate model and metrics are
logged to a dedicated retraining run, and the promotion/rollback decision is
appended to the same run id afterwards.
"""

from __future__ import annotations

import logging
import warnings
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ml.data import load_demand_training_table, subset_items_days
from ml.features import (
    FEATURE_COLUMNS,
    TARGET_COLUMN,
    build_features,
    drop_rows_with_incomplete_features,
)
from ml.metrics import compute_metrics
from ml.models.lightgbm_model import predict_lightgbm, train_lightgbm
from ml.split import temporal_train_test_split

from mlops.retraining._io import is_finite_number
from mlops.retraining.config import RetrainingConfig

logger = logging.getLogger(__name__)


def load_training_data(cfg: RetrainingConfig) -> pd.DataFrame:
    """Load + feature-engineer the demand table (deterministic subset in smoke)."""

    raw = load_demand_training_table(cfg.synthetic_dir)
    if cfg.max_items is not None and cfg.max_days is not None:
        raw = subset_items_days(raw, max_items=cfg.max_items, max_days=cfg.max_days)
    featured = build_features(raw)
    return drop_rows_with_incomplete_features(featured)


def data_reference(cfg: RetrainingConfig, featured: pd.DataFrame) -> dict[str, Any]:
    """A compact, auditable description of the data used for this run."""

    return {
        "synthetic_dir": str(cfg.synthetic_dir),
        "demand_history_file": "demand_history.csv",
        "parts_file": "parts.csv",
        "seed": cfg.random_seed,
        "max_items": cfg.max_items,
        "max_days": cfg.max_days,
        "rows": int(len(featured)),
        "num_items": int(featured["part_id"].nunique()),
    }


def verify_artifacts(featured: pd.DataFrame) -> dict[str, Any]:
    """Validate the engineered table before training (gate prerequisite)."""

    reasons: list[str] = []
    if featured.empty:
        reasons.append("Training table is empty.")

    missing_features = [c for c in FEATURE_COLUMNS if c not in featured.columns]
    if missing_features:
        reasons.append(f"Missing engineered feature columns: {missing_features}")

    nan_counts: dict[str, int] = {}
    for col in FEATURE_COLUMNS:
        if col in featured.columns:
            n = int(featured[col].isna().sum())
            if n:
                nan_counts[col] = n
    if nan_counts:
        reasons.append(f"NaN values present in features: {nan_counts}")

    target_ok = TARGET_COLUMN in featured.columns and bool(
        np.isfinite(featured[TARGET_COLUMN].to_numpy()).all()
    )
    if not target_ok:
        reasons.append("Target column missing or contains non-finite values.")

    if "date" in featured.columns:
        distinct_dates = int(pd.to_datetime(featured["date"]).nunique())
    else:
        distinct_dates = 0
        reasons.append("Missing 'date' column for temporal split.")
    if distinct_dates < 2:
        reasons.append("Need at least two distinct dates for a temporal split.")

    return {
        "passed": not reasons,
        "rows": int(len(featured)),
        "distinct_dates": distinct_dates,
        "feature_nan_counts": nan_counts,
        "target_finite": target_ok,
        "reasons": reasons,
    }


def _base_lgbm_params(
    cfg: RetrainingConfig, ml_config: dict[str, Any]
) -> dict[str, Any]:
    params = dict(ml_config.get("lightgbm", {}))
    params["random_state"] = cfg.random_seed
    params["n_estimators"] = cfg.lightgbm_n_estimators
    params.setdefault("verbose", -1)
    return params


def train_candidate(
    cfg: RetrainingConfig,
    featured: pd.DataFrame,
    ml_config: dict[str, Any],
) -> dict[str, Any]:
    """Train (optionally Optuna-tuned) candidate, evaluate on the test split.

    Returns a dict with candidate metrics, the trained params, the temporal
    split periods, the tuning summary (when enabled), and the held-out test
    frame so the champion can be re-evaluated on the SAME split.
    """

    train_fraction = ml_config.get("split", {}).get("train_fraction", 0.75)
    train_df, test_df = temporal_train_test_split(
        featured, train_fraction=train_fraction
    )
    base_params = _base_lgbm_params(cfg, ml_config)

    tuning_summary: dict[str, Any] = {"enabled": False}
    final_params = dict(base_params)

    if cfg.tune and cfg.optuna_trials > 0:
        # Carve a temporal validation slice from the *training* window so tuning
        # never sees the test set.
        sub_train, valid_df = temporal_train_test_split(
            train_df, train_fraction=0.8
        )
        from mlops.retraining.tuning import tune_lightgbm

        tuning_summary = tune_lightgbm(
            sub_train,
            valid_df,
            base_params,
            primary_metric=cfg.primary_metric,
            metric_direction=cfg.metric_direction,
            n_trials=cfg.optuna_trials,
            timeout_seconds=cfg.optuna_timeout_seconds,
            seed=cfg.random_seed,
        )
        final_params = tuning_summary["best_params"]

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model, features = train_lightgbm(train_df, final_params)
        preds = predict_lightgbm(model, test_df, features)
    metrics = compute_metrics(test_df[TARGET_COLUMN].to_numpy(), preds)

    return {
        "metrics": {k: float(v) for k, v in metrics.items()},
        "params": final_params,
        "feature_list": features,
        "tuning": tuning_summary,
        "train_period": (
            f"{train_df['date'].min().date()} to {train_df['date'].max().date()}"
        ),
        "test_period": (
            f"{test_df['date'].min().date()} to {test_df['date'].max().date()}"
        ),
        "train_rows": int(len(train_df)),
        "test_rows": int(len(test_df)),
        "_model": model,
        "_test_df": test_df,
        "_preds": preds,
    }


def evaluate_champion_on_test(
    cfg: RetrainingConfig,
    champion: dict[str, Any],
    test_df: pd.DataFrame,
    feature_list: list[str],
) -> dict[str, Any]:
    """Re-evaluate the champion model on the candidate's exact test split.

    Apples-to-apples comparison. Falls back to the champion's logged primary
    metric if the model cannot be loaded, and to ``None`` (first-run) when no
    champion exists at all.
    """

    result = {
        "metrics": None,
        "evaluation": "none",
        "warnings": list(champion.get("warnings", [])),
    }
    if not champion.get("available"):
        return result

    model_uri = champion.get("model_uri")
    if model_uri:
        try:
            import mlflow

            mlflow.set_tracking_uri(cfg.tracking_uri)
            model = mlflow.lightgbm.load_model(model_uri)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                preds = predict_lightgbm(model, test_df, feature_list)
            metrics = compute_metrics(test_df[TARGET_COLUMN].to_numpy(), preds)
            result["metrics"] = {k: float(v) for k, v in metrics.items()}
            result["evaluation"] = "re_evaluated_on_candidate_test_split"
            return result
        except Exception as exc:
            result["warnings"].append(
                f"Could not load/evaluate champion model from {model_uri} "
                f"({type(exc).__name__}: {exc}); falling back to logged metric."
            )

    # Fallback: champion's own logged primary metric (e.g. lightgbm_<metric>).
    logged = champion.get("logged_metrics", {})
    for key in (f"lightgbm_{cfg.primary_metric}", cfg.primary_metric):
        value = logged.get(key)
        if is_finite_number(value):
            result["metrics"] = {cfg.primary_metric: float(value)}
            result["evaluation"] = f"champion_logged_metric:{key}"
            return result

    result["warnings"].append(
        "Champion exists but no usable primary metric could be obtained."
    )
    return result


def build_error_analysis_payload(
    cfg: RetrainingConfig,
    test_df: pd.DataFrame,
    preds: np.ndarray,
    top_n: int = 10,
) -> dict[str, Any]:
    """Per-item absolute error breakdown from the candidate's test predictions."""

    from mlops.retraining.summary import build_error_analysis

    frame = test_df.copy()
    frame["_abs_error"] = np.abs(frame[TARGET_COLUMN].to_numpy() - preds)
    per_item = (
        frame.groupby("part_id", observed=True)["_abs_error"]
        .mean()
        .sort_values(ascending=False)
    )
    worst = [
        {"part_id": str(part_id), "mean_abs_error": round(float(err), 4)}
        for part_id, err in per_item.head(top_n).items()
    ]

    intermittent_block: dict[str, Any] | None = None
    if "demand_pattern_intermittent" in frame.columns:
        grouped = frame.groupby("demand_pattern_intermittent", observed=True)[
            "_abs_error"
        ].mean()
        intermittent_block = {
            "intermittent_mean_abs_error": round(
                float(grouped.get(1, float("nan"))), 4
            )
            if 1 in grouped.index
            else None,
            "regular_mean_abs_error": round(float(grouped.get(0, float("nan"))), 4)
            if 0 in grouped.index
            else None,
        }

    return build_error_analysis(
        available=True,
        worst_items_by_error=worst,
        intermittent_demand_items_error=intermittent_block,
        high_stockout_risk_items_error=None,
        notes=[
            "Per-item mean absolute error on the candidate's synthetic test "
            "split (seed 42); diagnostic only, not a production claim.",
            "High-stockout-risk item errors require PR-04 risk classification "
            "joined to the test split and are deferred to the model card / QA.",
        ],
    )


def load_cost_context(cfg: RetrainingConfig) -> dict[str, Any]:
    """Optional PR-04 cost-aware secondary context (never gates promotion)."""

    pr04_path = Path("artifacts/decision/decision_summary.json")
    if not pr04_path.exists():
        return {
            "cost_metric_available": False,
            "note": (
                "PR-04 decision_summary.json not found; cost-aware context "
                "deferred. Run `make decision-intel` to populate it."
            ),
        }
    try:
        import json

        summary = json.loads(pr04_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {
            "cost_metric_available": False,
            "note": f"Could not read PR-04 decision summary: {exc}",
        }
    cost = summary.get("cost_metrics", {})
    available = is_finite_number(cost.get("selected_pinball_loss"))
    return {
        "cost_metric_available": available,
        "source": str(pr04_path),
        "synthetic": True,
        "selected_pinball_loss": cost.get("selected_pinball_loss"),
        "cost_reduction_vs_best_baseline_pct": cost.get(
            "cost_reduction_vs_best_baseline_pct"
        ),
        # Deltas require a champion cost re-simulation, deferred honestly.
        "estimated_holding_cost_delta": None,
        "estimated_stockout_cost_delta": None,
        "estimated_total_inventory_cost_delta": None,
        "note": (
            "Cost figures are synthetic PR-04 context for observability only; "
            "candidate-vs-champion cost deltas require a champion cost "
            "re-simulation and are deferred."
        ),
    }


def package_versions() -> dict[str, Any]:
    """Record key package versions for reproducibility (best effort)."""

    versions: dict[str, Any] = {}
    for name in ("mlflow", "optuna", "zenml", "lightgbm", "pandas", "numpy"):
        try:
            import importlib.metadata as md

            versions[name] = md.version(name)
        except Exception:
            versions[name] = None
    return versions
