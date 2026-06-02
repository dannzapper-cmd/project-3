"""Feature engineering for demand forecasting baseline."""

from __future__ import annotations

import pandas as pd

FEATURE_COLUMNS: list[str] = [
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

CATEGORICAL_FEATURES: list[str] = ["part_id", "category_id", "supplier_id"]
TARGET_COLUMN = "quantity_demand"


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Generate calendar, lag, rolling, and metadata features per part series."""

    result = df.copy()
    result["date"] = pd.to_datetime(result["date"])
    result = result.sort_values(["part_id", "date"]).reset_index(drop=True)

    result["day_of_week"] = result["date"].dt.dayofweek
    result["month"] = result["date"].dt.month
    result["week_of_year"] = result["date"].dt.isocalendar().week.astype(int)
    result["is_weekend"] = (result["day_of_week"] >= 5).astype(int)

    grouped = result.groupby("part_id", group_keys=False)["quantity_demand"]
    for lag in (7, 14, 28):
        result[f"lag_{lag}"] = grouped.shift(lag)

    result["rolling_mean_7"] = grouped.transform(
        lambda s: s.shift(1).rolling(window=7, min_periods=1).mean()
    )
    result["rolling_mean_28"] = grouped.transform(
        lambda s: s.shift(1).rolling(window=28, min_periods=1).mean()
    )
    result["rolling_std_28"] = grouped.transform(
        lambda s: s.shift(1).rolling(window=28, min_periods=1).std()
    ).fillna(0.0)

    result["demand_pattern_intermittent"] = (
        result["demand_pattern"] == "intermittent"
    ).astype(int)

    result["category_id"] = result["category_id"].astype("category")
    result["supplier_id"] = result["supplier_id"].astype("category")
    result["part_id"] = result["part_id"].astype("category")

    return result


def drop_rows_with_incomplete_features(
    df: pd.DataFrame,
    feature_cols: list[str] | None = None,
) -> pd.DataFrame:
    """Drop rows where lag features are not yet available."""

    cols = feature_cols or FEATURE_COLUMNS
    return df.dropna(subset=cols).reset_index(drop=True)
