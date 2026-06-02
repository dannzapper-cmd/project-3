"""Tests for Pandera data validation."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from api.validation import (
    DataValidationError,
    validate_file,
    validate_processed_data,
    validate_synthetic_data,
)


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_minimal_synthetic_dataset(directory: Path) -> None:
    _write_csv(
        directory / "categories.csv",
        ["category_id", "name", "parent_id", "description"],
        [
            {
                "category_id": "CAT-001",
                "name": "Components",
                "parent_id": "",
                "description": "Components",
            }
        ],
    )
    _write_csv(
        directory / "suppliers.csv",
        ["supplier_id", "name", "country", "lead_time_days", "reliability_score"],
        [
            {
                "supplier_id": "SUP-001",
                "name": "Supplier",
                "country": "US",
                "lead_time_days": 7,
                "reliability_score": 0.95,
            }
        ],
    )
    _write_csv(
        directory / "parts.csv",
        [
            "part_id",
            "sku",
            "name",
            "category_id",
            "supplier_id",
            "unit_cost",
            "reorder_point",
            "safety_stock",
            "lead_time_days",
            "current_stock",
            "stockout_flag",
            "demand_pattern",
        ],
        [
            {
                "part_id": "PRT-001",
                "sku": "W-001",
                "name": "Widget",
                "category_id": "CAT-001",
                "supplier_id": "SUP-001",
                "unit_cost": 1.25,
                "reorder_point": 10,
                "safety_stock": 2,
                "lead_time_days": 7,
                "current_stock": 20,
                "stockout_flag": 0,
                "demand_pattern": "regular",
            }
        ],
    )
    _write_csv(
        directory / "stock_movements.csv",
        ["movement_id", "part_id", "date", "movement_type", "quantity", "reference"],
        [
            {
                "movement_id": "MOV-001",
                "part_id": "PRT-001",
                "date": "2024-01-01",
                "movement_type": "in",
                "quantity": 5,
                "reference": "INIT",
            }
        ],
    )
    _write_csv(
        directory / "demand_history.csv",
        ["part_id", "date", "quantity_demand", "stockout_flag", "demand_pattern"],
        [
            {
                "part_id": "PRT-001",
                "date": "2024-01-01",
                "quantity_demand": 3,
                "stockout_flag": 0,
                "demand_pattern": "regular",
            }
        ],
    )


def test_validate_synthetic_data_success(tmp_path: Path) -> None:
    _write_minimal_synthetic_dataset(tmp_path)

    counts = validate_synthetic_data(tmp_path)

    assert counts["parts.csv"] == 1
    assert counts["demand_history.csv"] == 1


def test_validate_synthetic_data_missing_column(tmp_path: Path) -> None:
    _write_minimal_synthetic_dataset(tmp_path)
    _write_csv(
        tmp_path / "suppliers.csv",
        ["supplier_id", "name", "country", "reliability_score"],
        [
            {
                "supplier_id": "SUP-001",
                "name": "Supplier",
                "country": "US",
                "reliability_score": 0.95,
            }
        ],
    )

    with pytest.raises(DataValidationError, match="lead_time_days"):
        validate_synthetic_data(tmp_path)


def test_validate_synthetic_data_negative_lead_time(tmp_path: Path) -> None:
    _write_minimal_synthetic_dataset(tmp_path)
    _write_csv(
        tmp_path / "suppliers.csv",
        ["supplier_id", "name", "country", "lead_time_days", "reliability_score"],
        [
            {
                "supplier_id": "SUP-001",
                "name": "Supplier",
                "country": "US",
                "lead_time_days": -1,
                "reliability_score": 0.95,
            }
        ],
    )

    with pytest.raises(DataValidationError, match="lead_time_days"):
        validate_synthetic_data(tmp_path)


def test_validate_synthetic_data_invalid_date(tmp_path: Path) -> None:
    _write_minimal_synthetic_dataset(tmp_path)
    _write_csv(
        tmp_path / "demand_history.csv",
        ["part_id", "date", "quantity_demand", "stockout_flag", "demand_pattern"],
        [
            {
                "part_id": "PRT-001",
                "date": "not-a-date",
                "quantity_demand": 3,
                "stockout_flag": 0,
                "demand_pattern": "regular",
            }
        ],
    )

    with pytest.raises(DataValidationError, match="date"):
        validate_synthetic_data(tmp_path)


def test_validate_processed_data_invalid_quantity(tmp_path: Path) -> None:
    _write_csv(
        tmp_path / "stock_records.csv",
        ["id", "part_id", "quantity", "location_id", "status", "batch"],
        [
            {
                "id": 1,
                "part_id": 10,
                "quantity": -3,
                "location_id": 2,
                "status": "ok",
                "batch": "B-1",
            }
        ],
    )

    with pytest.raises(DataValidationError, match="quantity"):
        validate_processed_data(tmp_path)


def test_validate_file_reports_missing_file(tmp_path: Path) -> None:
    from api.validation import SYNTHETIC_SCHEMAS

    with pytest.raises(DataValidationError, match="missing"):
        validate_file(tmp_path / "missing.csv", SYNTHETIC_SCHEMAS["parts.csv"])

