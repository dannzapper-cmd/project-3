"""Temporal reference/current split for offline drift monitoring.

The split mirrors the PR-03 forecasting philosophy: it is a strict temporal
boundary split (never a random sample). The reference window is the first
``reference_fraction`` of distinct sorted dates; the current window is the
remainder. This guarantees that no current-period date can appear in the
reference window, which would otherwise leak future information into the
drift baseline.
"""

from __future__ import annotations

import pandas as pd


class TemporalSplitError(ValueError):
    """Raised when a temporal reference/current split cannot be built."""


def temporal_reference_current_split(
    df: pd.DataFrame,
    *,
    reference_fraction: float = 0.80,
    date_col: str = "date",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split ``df`` into (reference, current) by a global date boundary.

    Reference = rows on the first ``reference_fraction`` of distinct dates.
    Current = rows on the remaining (most recent) dates.
    """

    if not 0.0 < reference_fraction < 1.0:
        raise TemporalSplitError("reference_fraction must be between 0 and 1")
    if date_col not in df.columns:
        raise TemporalSplitError(
            f"Missing required date column '{date_col}' for temporal split"
        )

    dates = pd.to_datetime(df[date_col])
    unique_dates = sorted(dates.unique())
    if len(unique_dates) < 2:
        raise TemporalSplitError(
            "Need at least two distinct dates for a temporal reference/current split"
        )

    split_index = max(1, int(len(unique_dates) * reference_fraction))
    if split_index >= len(unique_dates):
        split_index = len(unique_dates) - 1

    reference_cutoff = unique_dates[split_index - 1]
    reference_df = df[dates <= reference_cutoff].copy()
    current_df = df[dates > reference_cutoff].copy()

    if reference_df.empty or current_df.empty:
        raise TemporalSplitError(
            "Temporal split produced an empty reference or current window"
        )

    validate_no_temporal_leakage(reference_df, current_df, date_col=date_col)

    return (
        reference_df.reset_index(drop=True),
        current_df.reset_index(drop=True),
    )


def validate_no_temporal_leakage(
    reference_df: pd.DataFrame,
    current_df: pd.DataFrame,
    *,
    date_col: str = "date",
) -> None:
    """Assert the reference window strictly precedes the current window.

    Raises :class:`TemporalSplitError` if any current-period date is found in
    the reference window (or the boundary is not strict).
    """

    reference_dates = set(pd.to_datetime(reference_df[date_col]).unique())
    current_dates = set(pd.to_datetime(current_df[date_col]).unique())

    overlap = reference_dates.intersection(current_dates)
    if overlap:
        raise TemporalSplitError(
            f"Temporal leakage: {len(overlap)} date(s) appear in both the "
            "reference and current windows"
        )

    reference_max = pd.to_datetime(reference_df[date_col]).max()
    current_min = pd.to_datetime(current_df[date_col]).min()
    if not reference_max < current_min:
        raise TemporalSplitError(
            "Temporal leakage: reference max date must be strictly before the "
            f"current min date (reference_max={reference_max}, "
            f"current_min={current_min})"
        )


def split_periods(
    reference_df: pd.DataFrame,
    current_df: pd.DataFrame,
    *,
    date_col: str = "date",
) -> dict[str, str]:
    """Return human-readable reference/current period strings."""

    ref_dates = pd.to_datetime(reference_df[date_col])
    cur_dates = pd.to_datetime(current_df[date_col])
    return {
        "reference_period": f"{ref_dates.min().date()} to {ref_dates.max().date()}",
        "current_period": f"{cur_dates.min().date()} to {cur_dates.max().date()}",
        "reference_rows": str(len(reference_df)),
        "current_rows": str(len(current_df)),
    }
