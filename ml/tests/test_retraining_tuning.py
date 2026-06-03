"""Tests for bounded, deterministic Optuna tuning."""

from __future__ import annotations

import pytest

from ml.data import load_demand_training_table, subset_items_days
from ml.features import build_features, drop_rows_with_incomplete_features
from ml.split import temporal_train_test_split

optuna = pytest.importorskip("optuna")

from mlops.retraining.tuning import tune_lightgbm  # noqa: E402


@pytest.fixture
def small_splits(synthetic_dir):
    raw = load_demand_training_table(synthetic_dir)
    raw = subset_items_days(raw, max_items=8, max_days=90)
    featured = drop_rows_with_incomplete_features(build_features(raw))
    train_df, valid_df = temporal_train_test_split(featured, train_fraction=0.8)
    return train_df, valid_df


def test_tuning_is_bounded_and_records_trials(small_splits):
    train_df, valid_df = small_splits
    result = tune_lightgbm(
        train_df,
        valid_df,
        {"n_estimators": 40, "verbose": -1},
        n_trials=2,
        timeout_seconds=60,
        seed=42,
    )
    assert result["enabled"] is True
    assert result["n_trials_completed"] <= 2
    assert result["sampler"] == "TPESampler"
    assert result["seed"] == 42
    # Each recorded trial carries the audit fields used in optuna_trials.csv.
    for trial in result["trials"]:
        assert set(trial) >= {
            "trial_number",
            "params",
            "value",
            "state",
            "duration_seconds",
        }


def test_tuning_is_deterministic_for_fixed_seed(small_splits):
    train_df, valid_df = small_splits
    base = {"n_estimators": 40, "verbose": -1}
    a = tune_lightgbm(train_df, valid_df, base, n_trials=2, seed=42)
    b = tune_lightgbm(train_df, valid_df, base, n_trials=2, seed=42)
    assert a["best_value"] == b["best_value"]
    # Sampled hyperparameters match exactly across identical-seed runs.
    assert [t["params"] for t in a["trials"]] == [t["params"] for t in b["trials"]]
