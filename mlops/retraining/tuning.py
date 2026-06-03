"""Bounded, deterministic Optuna tuning for the demand-forecast candidate.

Scope: tune only the main LightGBM demand-forecasting candidate (the existing
PR-03 primary model). The objective is the SAME primary metric used by
PR-03/PR-04/PR-05 (MAE by default, lower is better) on the temporal holdout, so
no new metric definition is introduced.

Safety:

* Trial count is already clamped by :func:`mlops.retraining.config.clamp_trials`
  before reaching here; this module also passes a ``timeout`` to
  ``study.optimize`` so tuning can never run unbounded.
* ``TPESampler(seed=...)`` makes the search deterministic for a given seed.
* Optuna's experimental storage warnings are suppressed cleanly.
"""

from __future__ import annotations

import time
import warnings
from typing import Any

import pandas as pd

from ml.features import TARGET_COLUMN
from ml.metrics import compute_metrics
from ml.models.lightgbm_model import predict_lightgbm, train_lightgbm

# A deliberately small, sensible search space around the PR-03 defaults.
_SEARCH_SPACE = {
    "learning_rate": (0.02, 0.15),
    "num_leaves": (15, 63),
    "min_child_samples": (10, 40),
    "subsample": (0.6, 1.0),
    "colsample_bytree": (0.6, 1.0),
}


def _suggest_params(trial: Any, base_params: dict[str, Any]) -> dict[str, Any]:
    params = dict(base_params)
    lr_lo, lr_hi = _SEARCH_SPACE["learning_rate"]
    nl_lo, nl_hi = _SEARCH_SPACE["num_leaves"]
    mcs_lo, mcs_hi = _SEARCH_SPACE["min_child_samples"]
    ss_lo, ss_hi = _SEARCH_SPACE["subsample"]
    cs_lo, cs_hi = _SEARCH_SPACE["colsample_bytree"]
    params.update(
        learning_rate=trial.suggest_float("learning_rate", lr_lo, lr_hi, log=True),
        num_leaves=trial.suggest_int("num_leaves", nl_lo, nl_hi),
        min_child_samples=trial.suggest_int("min_child_samples", mcs_lo, mcs_hi),
        subsample=trial.suggest_float("subsample", ss_lo, ss_hi),
        colsample_bytree=trial.suggest_float("colsample_bytree", cs_lo, cs_hi),
    )
    return params


def tune_lightgbm(
    train_df: pd.DataFrame,
    valid_df: pd.DataFrame,
    base_params: dict[str, Any],
    *,
    primary_metric: str = "mae",
    metric_direction: str = "lower_is_better",
    n_trials: int = 2,
    timeout_seconds: int = 60,
    seed: int = 42,
) -> dict[str, Any]:
    """Run a small Optuna study; return best params + a trials summary.

    The returned ``best_params`` are merged onto ``base_params`` and are safe to
    pass straight back into :func:`ml.models.lightgbm_model.train_lightgbm`.
    """

    import optuna
    from optuna.samplers import TPESampler

    optuna.logging.set_verbosity(optuna.logging.WARNING)

    y_valid = valid_df[TARGET_COLUMN].to_numpy()
    direction = "minimize" if metric_direction == "lower_is_better" else "maximize"

    trial_records: list[dict[str, Any]] = []

    def objective(trial: Any) -> float:
        started = time.monotonic()
        params = _suggest_params(trial, base_params)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model, features = train_lightgbm(train_df, params)
            preds = predict_lightgbm(model, valid_df, features)
        metrics = compute_metrics(y_valid, preds)
        value = float(metrics[primary_metric])
        trial_records.append(
            {
                "trial_number": trial.number,
                "params": {
                    k: params[k] for k in _SEARCH_SPACE if k in params
                },
                "value": value,
                "state": "COMPLETE",
                "duration_seconds": round(time.monotonic() - started, 4),
            }
        )
        return value

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=optuna.exceptions.ExperimentalWarning)
        study = optuna.create_study(
            direction=direction,
            sampler=TPESampler(seed=seed),
        )
        study.optimize(
            objective,
            n_trials=n_trials,
            timeout=timeout_seconds,
            show_progress_bar=False,
        )

    best_params = dict(base_params)
    best_params.update(study.best_params)
    return {
        "enabled": True,
        "n_trials_requested": n_trials,
        "n_trials_completed": len(trial_records),
        "timeout_seconds": timeout_seconds,
        "seed": seed,
        "sampler": "TPESampler",
        "direction": direction,
        "primary_metric": primary_metric,
        "best_value": float(study.best_value),
        "best_params": best_params,
        "trials": trial_records,
    }
