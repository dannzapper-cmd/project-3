"""Pandera validation for InvForge synthetic and processed datasets."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import pandera.pandas as pa
from pandera.errors import SchemaErrors


class DataValidationError(RuntimeError):
    """Raised when a dataset does not match its schema."""


def _valid_dates(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce").notna()


SYNTHETIC_SCHEMAS: dict[str, pa.DataFrameSchema] = {
    "categories.csv": pa.DataFrameSchema(
        {
            "category_id": pa.Column(str, coerce=True),
            "name": pa.Column(str, pa.Check.str_length(min_value=1), coerce=True),
            "parent_id": pa.Column(str, nullable=True, coerce=True),
            "description": pa.Column(str, nullable=True, coerce=True),
        },
        strict=True,
    ),
    "suppliers.csv": pa.DataFrameSchema(
        {
            "supplier_id": pa.Column(str, coerce=True),
            "name": pa.Column(str, pa.Check.str_length(min_value=1), coerce=True),
            "country": pa.Column(str, pa.Check.str_length(min_value=2), coerce=True),
            "lead_time_days": pa.Column(
                int,
                pa.Check.ge(0, error="lead_time_days must be non-negative"),
                coerce=True,
            ),
            "reliability_score": pa.Column(
                float,
                [
                    pa.Check.ge(0.0, error="reliability_score must be >= 0"),
                    pa.Check.le(1.0, error="reliability_score must be <= 1"),
                ],
                coerce=True,
            ),
        },
        strict=True,
    ),
    "parts.csv": pa.DataFrameSchema(
        {
            "part_id": pa.Column(str, coerce=True),
            "sku": pa.Column(str, pa.Check.str_length(min_value=1), coerce=True),
            "name": pa.Column(str, pa.Check.str_length(min_value=1), coerce=True),
            "category_id": pa.Column(str, coerce=True),
            "supplier_id": pa.Column(str, coerce=True),
            "unit_cost": pa.Column(
                float,
                pa.Check.ge(0.0, error="unit_cost must be non-negative"),
                coerce=True,
            ),
            "reorder_point": pa.Column(
                float,
                pa.Check.ge(0.0, error="reorder_point must be non-negative"),
                coerce=True,
            ),
            "safety_stock": pa.Column(
                float,
                pa.Check.ge(0.0, error="safety_stock must be non-negative"),
                coerce=True,
            ),
            "lead_time_days": pa.Column(
                int,
                pa.Check.ge(0, error="lead_time_days must be non-negative"),
                coerce=True,
            ),
            "current_stock": pa.Column(
                float,
                pa.Check.ge(0.0, error="current_stock must be non-negative"),
                coerce=True,
            ),
            "stockout_flag": pa.Column(
                int,
                pa.Check.isin([0, 1], error="stockout_flag must be 0 or 1"),
                coerce=True,
            ),
            "demand_pattern": pa.Column(
                str,
                pa.Check.isin(
                    ["regular", "intermittent"],
                    error="demand_pattern must be regular or intermittent",
                ),
                coerce=True,
            ),
        },
        strict=True,
    ),
    "stock_movements.csv": pa.DataFrameSchema(
        {
            "movement_id": pa.Column(str, coerce=True),
            "part_id": pa.Column(str, coerce=True),
            "date": pa.Column(
                str,
                pa.Check(_valid_dates, error="date must be parseable"),
                coerce=True,
            ),
            "movement_type": pa.Column(
                str,
                pa.Check.isin(
                    ["in", "out", "adjustment"],
                    error="movement_type must be in, out, or adjustment",
                ),
                coerce=True,
            ),
            "quantity": pa.Column(float, coerce=True),
            "reference": pa.Column(str, nullable=True, coerce=True),
        },
        strict=True,
    ),
    "demand_history.csv": pa.DataFrameSchema(
        {
            "part_id": pa.Column(str, coerce=True),
            "date": pa.Column(
                str,
                pa.Check(_valid_dates, error="date must be parseable"),
                coerce=True,
            ),
            "quantity_demand": pa.Column(
                float,
                pa.Check.ge(0.0, error="quantity_demand must be non-negative"),
                coerce=True,
            ),
            "stockout_flag": pa.Column(
                int,
                pa.Check.isin([0, 1], error="stockout_flag must be 0 or 1"),
                coerce=True,
            ),
            "demand_pattern": pa.Column(
                str,
                pa.Check.isin(
                    ["regular", "intermittent"],
                    error="demand_pattern must be regular or intermittent",
                ),
                coerce=True,
            ),
        },
        strict=True,
    ),
}


PROCESSED_SCHEMAS: dict[str, pa.DataFrameSchema] = {
    "parts.csv": pa.DataFrameSchema(
        {
            "id": pa.Column(str, coerce=True),
            "name": pa.Column(str, pa.Check.str_length(min_value=1), coerce=True),
            "description": pa.Column(str, nullable=True, coerce=True),
            "ipn": pa.Column(str, nullable=True, coerce=True),
            "category_id": pa.Column(str, nullable=True, coerce=True),
            "active": pa.Column(object, nullable=True),
            "virtual": pa.Column(object, nullable=True),
        },
        strict=True,
    ),
    "stock_records.csv": pa.DataFrameSchema(
        {
            "id": pa.Column(str, coerce=True),
            "part_id": pa.Column(str, nullable=True, coerce=True),
            "quantity": pa.Column(
                float,
                pa.Check.ge(0.0, error="quantity must be non-negative"),
                coerce=True,
            ),
            "location_id": pa.Column(str, nullable=True, coerce=True),
            "status": pa.Column(object, nullable=True),
            "batch": pa.Column(str, nullable=True, coerce=True),
        },
        strict=True,
    ),
    "categories.csv": pa.DataFrameSchema(
        {
            "id": pa.Column(str, coerce=True),
            "name": pa.Column(str, pa.Check.str_length(min_value=1), coerce=True),
            "parent_id": pa.Column(str, nullable=True, coerce=True),
            "description": pa.Column(str, nullable=True, coerce=True),
        },
        strict=True,
    ),
    "companies.csv": pa.DataFrameSchema(
        {
            "id": pa.Column(str, coerce=True),
            "name": pa.Column(str, pa.Check.str_length(min_value=1), coerce=True),
            "is_supplier": pa.Column(object, nullable=True),
            "is_manufacturer": pa.Column(object, nullable=True),
            "is_customer": pa.Column(object, nullable=True),
        },
        strict=True,
    ),
}


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, keep_default_na=False)


def validate_file(path: Path, schema: pa.DataFrameSchema) -> pd.DataFrame:
    """Validate one CSV file and return the coerced DataFrame."""

    try:
        dataframe = _read_csv(path)
        return schema.validate(dataframe, lazy=True)
    except SchemaErrors as exc:
        failure_cases = exc.failure_cases.to_string(index=False)
        raise DataValidationError(
            f"Validation failed for {path}: {failure_cases}"
        ) from exc
    except FileNotFoundError as exc:
        raise DataValidationError(f"Required data file is missing: {path}") from exc


def validate_directory(
    directory: Path,
    schemas: dict[str, pa.DataFrameSchema],
    *,
    require_all: bool,
) -> dict[str, int]:
    """Validate CSV files in a directory and return row counts."""

    row_counts: dict[str, int] = {}
    for filename, schema in schemas.items():
        path = directory / filename
        if not path.exists():
            if require_all:
                raise DataValidationError(f"Required data file is missing: {path}")
            continue
        row_counts[filename] = len(validate_file(path, schema))
    return row_counts


def validate_synthetic_data(directory: Path) -> dict[str, int]:
    return validate_directory(directory, SYNTHETIC_SCHEMAS, require_all=True)


def validate_processed_data(directory: Path) -> dict[str, int]:
    return validate_directory(directory, PROCESSED_SCHEMAS, require_all=False)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate InvForge data artifacts.")
    parser.add_argument(
        "--synthetic-dir",
        type=Path,
        default=Path("data/synthetic/output"),
        help="Directory containing generated synthetic CSV files.",
    )
    parser.add_argument(
        "--processed-dir",
        type=Path,
        default=Path("data/processed"),
        help="Directory containing processed InvenTree CSV files.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    synthetic_counts = validate_synthetic_data(args.synthetic_dir)
    processed_counts = validate_processed_data(args.processed_dir)
    print(f"Validated synthetic data: {synthetic_counts}")
    if processed_counts:
        print(f"Validated processed data: {processed_counts}")
    else:
        print(f"No processed CSV files found under {args.processed_dir}; skipped.")


if __name__ == "__main__":
    main()

