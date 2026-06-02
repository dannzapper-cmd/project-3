"""Time-based train/test splitting for demand forecasting."""

from __future__ import annotations

import pandas as pd


def temporal_train_test_split(
    df: pd.DataFrame,
    *,
    train_fraction: float = 0.75,
    date_col: str = "date",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split by global date range: first ``train_fraction`` for train, rest for test."""

    if not 0.0 < train_fraction < 1.0:
        raise ValueError("train_fraction must be between 0 and 1")

    dates = pd.to_datetime(df[date_col])
    unique_dates = sorted(dates.unique())
    if len(unique_dates) < 2:
        raise ValueError("Need at least two distinct dates for temporal split")

    split_index = max(1, int(len(unique_dates) * train_fraction))
    if split_index >= len(unique_dates):
        split_index = len(unique_dates) - 1

    train_cutoff = unique_dates[split_index - 1]
    train_df = df[dates <= train_cutoff].copy()
    test_df = df[dates > train_cutoff].copy()

    assert train_df[date_col].max() < test_df[date_col].min(), (
        "Temporal leakage: train max date must be strictly before test min date"
    )

    return train_df.reset_index(drop=True), test_df.reset_index(drop=True)
