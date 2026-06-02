"""Tests for the PR-05 temporal reference/current split (no leakage)."""

from __future__ import annotations

import pandas as pd
import pytest

from ml.features import build_features, drop_rows_with_incomplete_features
from mlops.splitting import (
    TemporalSplitError,
    split_periods,
    temporal_reference_current_split,
    validate_no_temporal_leakage,
)


def test_reference_current_split_no_leakage(demand_table):
    featured = drop_rows_with_incomplete_features(build_features(demand_table))
    reference_df, current_df = temporal_reference_current_split(
        featured, reference_fraction=0.80
    )
    assert reference_df["date"].max() < current_df["date"].min()
    overlap = set(reference_df["date"].unique()) & set(current_df["date"].unique())
    assert not overlap


def test_reference_current_split_is_not_random_sample(demand_table):
    featured = drop_rows_with_incomplete_features(build_features(demand_table))
    reference_df, current_df = temporal_reference_current_split(
        featured, reference_fraction=0.80
    )
    all_ref = set(reference_df["date"].unique())
    all_cur = set(current_df["date"].unique())
    # Reference must contain the earliest date; current must contain the latest.
    assert min(featured["date"]) in all_ref
    assert max(featured["date"]) in all_cur


def test_split_rejects_invalid_fraction(demand_table):
    featured = drop_rows_with_incomplete_features(build_features(demand_table))
    with pytest.raises(TemporalSplitError):
        temporal_reference_current_split(featured, reference_fraction=1.5)


def test_split_requires_two_dates():
    df = pd.DataFrame({"date": pd.to_datetime(["2024-01-01", "2024-01-01"])})
    with pytest.raises(TemporalSplitError):
        temporal_reference_current_split(df)


def test_validate_no_temporal_leakage_detects_overlap():
    ref = pd.DataFrame({"date": pd.to_datetime(["2024-01-01", "2024-01-02"])})
    cur = pd.DataFrame({"date": pd.to_datetime(["2024-01-02", "2024-01-03"])})
    with pytest.raises(TemporalSplitError):
        validate_no_temporal_leakage(ref, cur)


def test_split_periods_schema(demand_table):
    featured = drop_rows_with_incomplete_features(build_features(demand_table))
    reference_df, current_df = temporal_reference_current_split(featured)
    periods = split_periods(reference_df, current_df)
    assert set(periods) == {
        "reference_period",
        "current_period",
        "reference_rows",
        "current_rows",
    }
