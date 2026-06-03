"""Tests for retraining configuration + hard Optuna bounds."""

from __future__ import annotations

from mlops.retraining.config import (
    FULL_MAX_TRIALS,
    SMOKE_MAX_TRIALS,
    RetrainingConfig,
    clamp_trials,
    load_retraining_config,
)


def test_smoke_config_is_small_and_deterministic():
    cfg = load_retraining_config(mode="smoke")
    assert cfg.mode == "smoke"
    assert cfg.random_seed == 42
    assert cfg.primary_metric == "mae"
    assert cfg.metric_direction == "lower_is_better"
    # Smoke must stay small and bounded.
    assert cfg.optuna_trials <= SMOKE_MAX_TRIALS
    assert cfg.max_items is not None and cfg.max_items <= 20


def test_optuna_trials_hard_cap_smoke():
    trials, warnings = clamp_trials("smoke", 50)
    assert trials == SMOKE_MAX_TRIALS
    assert warnings


def test_optuna_trials_hard_cap_full():
    trials, warnings = clamp_trials("full", 1000)
    assert trials == FULL_MAX_TRIALS
    assert warnings


def test_env_override_trials_still_clamped(monkeypatch):
    monkeypatch.setenv("RETRAINING_OPTUNA_TRIALS", "99")
    cfg = load_retraining_config(mode="smoke")
    assert cfg.optuna_trials <= SMOKE_MAX_TRIALS


def test_env_override_promotion_threshold(monkeypatch):
    monkeypatch.setenv("RETRAINING_PROMOTION_THRESHOLD", "7.5")
    cfg = load_retraining_config(mode="smoke")
    assert cfg.promotion_threshold_pct == 7.5


def test_config_roundtrip_to_dict():
    cfg = load_retraining_config(mode="smoke")
    restored = RetrainingConfig.from_dict(cfg.to_dict())
    assert restored == cfg
    # Paths survive the round-trip as Path objects.
    assert str(restored.artifacts_dir) == str(cfg.artifacts_dir)
