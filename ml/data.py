"""Load and prepare demand forecasting training data from synthetic CSVs."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def load_demand_training_table(
    synthetic_dir: Path,
    *,
    demand_file: str = "demand_history.csv",
    parts_file: str = "parts.csv",
) -> pd.DataFrame:
    """Build a demand-history training table with part metadata (no stock fields)."""

    demand_path = synthetic_dir / demand_file
    parts_path = synthetic_dir / parts_file

    if not demand_path.exists():
        raise FileNotFoundError(
            f"Demand history not found at {demand_path}. "
            "Run `make generate-data` first."
        )
    if not parts_path.exists():
        raise FileNotFoundError(
            f"Parts metadata not found at {parts_path}. "
            "Run `make generate-data` first."
        )

    demand = pd.read_csv(demand_path, parse_dates=["date"])
    parts = pd.read_csv(parts_path)

    metadata_cols = ["part_id", "category_id", "supplier_id", "lead_time_days"]
    if "demand_pattern" not in demand.columns:
        metadata_cols.append("demand_pattern")
    parts_meta = parts[metadata_cols].drop_duplicates(subset=["part_id"])

    merged = demand.merge(parts_meta, on="part_id", how="left")

    merged = merged.sort_values(["part_id", "date"]).reset_index(drop=True)
    return merged


def subset_items_days(
    df: pd.DataFrame,
    *,
    max_items: int,
    max_days: int,
) -> pd.DataFrame:
    """Return a small deterministic subset for smoke tests."""

    items = sorted(df["part_id"].unique())[:max_items]
    subset = df[df["part_id"].isin(items)].copy()
    dates = sorted(subset["date"].unique())[:max_days]
    return subset[subset["date"].isin(dates)].reset_index(drop=True)
