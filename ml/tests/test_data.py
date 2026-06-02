"""Tests for data loading and temporal split."""

from __future__ import annotations

from ml.data import subset_items_days
from ml.features import build_features, drop_rows_with_incomplete_features
from ml.split import temporal_train_test_split


def test_temporal_split_no_leakage(demand_table):
    featured = drop_rows_with_incomplete_features(build_features(demand_table))
    train_df, test_df = temporal_train_test_split(featured, train_fraction=0.75)
    assert train_df["date"].max() < test_df["date"].min()


def test_test_features_have_no_nan(demand_table):
    featured = drop_rows_with_incomplete_features(build_features(demand_table))
    _, test_df = temporal_train_test_split(featured, train_fraction=0.75)
    feature_cols = [
        "day_of_week",
        "month",
        "week_of_year",
        "is_weekend",
        "lag_7",
        "lag_14",
        "lag_28",
        "rolling_mean_7",
        "rolling_mean_28",
        "rolling_std_28",
        "category_id",
        "supplier_id",
        "lead_time_days",
        "demand_pattern_intermittent",
    ]
    assert not test_df[feature_cols].isna().any().any()


def test_load_demand_training_table_has_metadata(demand_table):
    assert "category_id" in demand_table.columns
    assert "supplier_id" in demand_table.columns
    assert "lead_time_days" in demand_table.columns
    assert "current_stock" not in demand_table.columns
    assert "reorder_point" not in demand_table.columns


def test_subset_items_days(demand_table):
    small = subset_items_days(demand_table, max_items=10, max_days=30)
    assert small["part_id"].nunique() <= 10
    assert small["date"].nunique() <= 30
