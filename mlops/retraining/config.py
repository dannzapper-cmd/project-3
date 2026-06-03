"""Configuration for the PR-09 retraining pipeline.

Values come from the ``retraining:`` section of ``mlops/config.yaml`` (the
existing MLOps config), with a small set of environment overrides for
cron/CI-friendly runs. Hard bounds on Optuna trials are enforced here in code,
not as soft defaults: smoke mode is capped at 3 trials, full mode at 20, so a
config edit can never trigger expensive tuning.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mlops.config import DEFAULT_MLOPS_CONFIG_PATH, load_mlops_config

# Non-negotiable trial ceilings (AA-5).
SMOKE_MAX_TRIALS = 3
FULL_MAX_TRIALS = 20

VALID_MODES = ("smoke", "full")

# Fields stored as filesystem paths (serialized as strings in ``to_dict``).
_PATH_FIELDS = ("artifacts_dir", "synthetic_dir", "ml_config_path")


def _as_optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


@dataclass(frozen=True)
class RetrainingConfig:
    """Resolved, immutable retraining configuration for a single run."""

    mode: str
    pipeline_name: str
    model_name: str
    primary_metric: str
    metric_direction: str
    promotion_threshold_pct: float
    random_seed: int
    artifacts_dir: Path

    # Data sub-sampling (smoke uses small deterministic subsets).
    max_items: int | None
    max_days: int | None
    lightgbm_n_estimators: int

    # Optuna tuning.
    tune: bool
    optuna_trials: int
    optuna_timeout_seconds: int

    # MLflow / registry.
    tracking_uri: str
    experiment_name: str
    forecast_experiment: str
    registered_model_name: str
    champion_alias: str
    previous_champion_alias: str
    model_artifact: str
    candidate_tag: str

    # BentoML packaging (reused from PR-05 only after a promotion).
    bentoml_enabled: bool
    bentoml_model_name: str

    # Paths to the synthetic data / ml config (read-only references).
    synthetic_dir: Path
    ml_config_path: Path

    warnings: list[str] = field(default_factory=list)

    @property
    def is_smoke(self) -> bool:
        return self.mode == "smoke"

    def as_reference(self) -> dict[str, Any]:
        """Compact, JSON-safe snapshot of the config for the audit summary."""

        return {
            "mode": self.mode,
            "pipeline_name": self.pipeline_name,
            "model_name": self.model_name,
            "primary_metric": self.primary_metric,
            "metric_direction": self.metric_direction,
            "promotion_threshold_pct": self.promotion_threshold_pct,
            "random_seed": self.random_seed,
            "max_items": self.max_items,
            "max_days": self.max_days,
            "lightgbm_n_estimators": self.lightgbm_n_estimators,
            "tune": self.tune,
            "optuna_trials": self.optuna_trials,
            "optuna_timeout_seconds": self.optuna_timeout_seconds,
            "tracking_uri": self.tracking_uri,
            "experiment_name": self.experiment_name,
            "registered_model_name": self.registered_model_name,
            "champion_alias": self.champion_alias,
            "previous_champion_alias": self.previous_champion_alias,
            "bentoml_enabled": self.bentoml_enabled,
        }

    def to_dict(self) -> dict[str, Any]:
        """Fully JSON-serializable dict (used to pass config to ZenML steps).

        ZenML runs steps in isolated contexts, so the config is threaded through
        as a plain-dict step parameter rather than a module global.
        """

        data: dict[str, Any] = {}
        for f in self.__dataclass_fields__:
            value = getattr(self, f)
            data[f] = str(value) if f in _PATH_FIELDS else value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RetrainingConfig:
        """Reconstruct a config from :meth:`to_dict` output."""

        kwargs = dict(data)
        for f in _PATH_FIELDS:
            if f in kwargs and kwargs[f] is not None:
                kwargs[f] = Path(kwargs[f])
        kwargs["warnings"] = list(kwargs.get("warnings", []))
        return cls(**kwargs)


def clamp_trials(mode: str, requested: int) -> tuple[int, list[str]]:
    """Clamp the requested Optuna trial count to the hard ceiling for ``mode``."""

    warnings: list[str] = []
    requested = max(0, int(requested))
    ceiling = SMOKE_MAX_TRIALS if mode == "smoke" else FULL_MAX_TRIALS
    if requested > ceiling:
        warnings.append(
            f"Requested optuna_trials={requested} exceeds the {mode}-mode hard "
            f"cap of {ceiling}; clamped to {ceiling}."
        )
        requested = ceiling
    return requested, warnings


def load_retraining_config(
    *,
    mode: str | None = None,
    tune: bool | None = None,
    config_path: Path = DEFAULT_MLOPS_CONFIG_PATH,
) -> RetrainingConfig:
    """Build a :class:`RetrainingConfig` from YAML + environment overrides.

    Environment overrides (cron/CI friendly):

    * ``RETRAINING_MODE`` (smoke|full)
    * ``RETRAINING_OPTUNA_TRIALS``
    * ``RETRAINING_PROMOTION_THRESHOLD``
    * ``RETRAINING_RANDOM_SEED``
    * ``MLFLOW_TRACKING_URI``
    """

    raw = load_mlops_config(config_path)
    rt = raw.get("retraining", {})
    mlflow_cfg = rt.get("mlflow", {})
    bento_cfg = rt.get("bentoml", {})
    data_cfg = raw.get("data", {})

    resolved_mode = (mode or os.environ.get("RETRAINING_MODE") or "smoke").lower()
    if resolved_mode not in VALID_MODES:
        raise ValueError(
            f"Unknown retraining mode '{resolved_mode}'; expected one of "
            f"{VALID_MODES}."
        )

    mode_cfg = rt.get("modes", {}).get(resolved_mode, {})
    warnings: list[str] = []

    # Tuning enabled? Explicit arg > env > config default.
    if tune is None:
        env_tune = os.environ.get("RETRAINING_TUNE")
        if env_tune is not None:
            tune = env_tune.strip().lower() in {"1", "true", "yes", "on"}
        else:
            tune = bool(rt.get("optuna", {}).get("enabled_default", False))

    requested_trials = mode_cfg.get("optuna_trials", 2)
    env_trials = os.environ.get("RETRAINING_OPTUNA_TRIALS")
    if env_trials is not None:
        requested_trials = int(env_trials)
    optuna_trials, trial_warnings = clamp_trials(resolved_mode, requested_trials)
    warnings.extend(trial_warnings)

    promotion_threshold = float(
        os.environ.get(
            "RETRAINING_PROMOTION_THRESHOLD",
            rt.get("promotion_threshold_pct", 5.0),
        )
    )
    random_seed = int(
        os.environ.get("RETRAINING_RANDOM_SEED", rt.get("random_seed", 42))
    )
    tracking_uri = os.environ.get(
        "MLFLOW_TRACKING_URI", mlflow_cfg.get("tracking_uri", "mlruns")
    )

    return RetrainingConfig(
        mode=resolved_mode,
        pipeline_name=rt.get("pipeline_name", "invforge_retraining"),
        model_name=mlflow_cfg.get("registered_model_name", "demand_forecast"),
        primary_metric=rt.get("primary_metric", "mae"),
        metric_direction=rt.get("metric_direction", "lower_is_better"),
        promotion_threshold_pct=promotion_threshold,
        random_seed=random_seed,
        artifacts_dir=Path(rt.get("artifacts_dir", "artifacts/retraining")),
        max_items=_as_optional_int(mode_cfg.get("max_items")),
        max_days=_as_optional_int(mode_cfg.get("max_days")),
        lightgbm_n_estimators=int(mode_cfg.get("lightgbm_n_estimators", 200)),
        tune=bool(tune),
        optuna_trials=optuna_trials,
        optuna_timeout_seconds=int(mode_cfg.get("optuna_timeout_seconds", 600)),
        tracking_uri=tracking_uri,
        experiment_name=mlflow_cfg.get(
            "experiment_name", "demand_forecast_retraining"
        ),
        forecast_experiment=mlflow_cfg.get(
            "forecast_experiment", "demand_forecast_baseline"
        ),
        registered_model_name=mlflow_cfg.get(
            "registered_model_name", "demand_forecast"
        ),
        champion_alias=mlflow_cfg.get("champion_alias", "champion"),
        previous_champion_alias=mlflow_cfg.get(
            "previous_champion_alias", "previous_champion"
        ),
        model_artifact=mlflow_cfg.get("model_artifact", "lightgbm_model"),
        candidate_tag=mlflow_cfg.get("candidate_tag", "pr09_candidate_run_id"),
        bentoml_enabled=bool(bento_cfg.get("enabled", False)),
        bentoml_model_name=bento_cfg.get(
            "model_name", "invforge_demand_forecast"
        ),
        synthetic_dir=Path(data_cfg.get("synthetic_dir", "data/synthetic/output")),
        ml_config_path=Path("ml/config.yaml"),
        warnings=warnings,
    )
