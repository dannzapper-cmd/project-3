"""Tests for StatsForecast pattern-specific model selection."""

from __future__ import annotations

from ml.features import build_features, drop_rows_with_incomplete_features
from ml.models.statsforecast_model import (
    INTERMITTENT_MODELS,
    REGULAR_MODELS,
    fit_predict_statsforecast,
)
from ml.split import temporal_train_test_split


def test_croston_sba_only_for_intermittent(demand_table):
    featured = drop_rows_with_incomplete_features(build_features(demand_table))
    train_df, test_df = temporal_train_test_split(featured, train_fraction=0.75)

    parts_patterns = (
        demand_table.drop_duplicates("part_id")
        .set_index("part_id")["demand_pattern"]
        .to_dict()
    )

    _, model_usage = fit_predict_statsforecast(
        train_df,
        test_df,
        parts_patterns,
        season_length=7,
        regular_model_names=["AutoETS", "SeasonalNaive"],
        intermittent_model_names=["CrostonClassic", "SBA"],
    )

    for name in model_usage.get("regular", []):
        assert name in REGULAR_MODELS, f"{name} must not be used for regular items"

    for name in model_usage.get("intermittent", []):
        assert name in INTERMITTENT_MODELS, (
            f"{name} must only be used for intermittent items"
        )

    assert model_usage.get("intermittent"), "Expected intermittent models to be used"
    assert model_usage.get("regular"), "Expected regular models to be used"
