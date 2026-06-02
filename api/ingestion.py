"""Inventory ingestion pipeline for the InvForge sidecar."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from api.inventree import InvenTreeClient


@dataclass(frozen=True)
class IngestionResult:
    """Summary returned by an InvenTree ingestion run."""

    raw_dir: Path
    processed_dir: Path
    raw_counts: dict[str, int]
    processed_files: dict[str, Path]


def _value(record: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = record.get(key)
        if value is not None:
            return value
    return ""


def _nested_id(value: Any) -> Any:
    if isinstance(value, dict):
        return _value(value, "pk", "id")
    return value if value is not None else ""


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, default=str))
            handle.write("\n")


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _normalize_parts(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in records:
        rows.append(
            {
                "id": _value(record, "pk", "id"),
                "name": _value(record, "name"),
                "description": _value(record, "description"),
                "ipn": _value(record, "IPN", "ipn"),
                "category_id": _nested_id(_value(record, "category")),
                "active": _value(record, "active"),
                "virtual": _value(record, "virtual"),
            }
        )
    return rows


def _normalize_stock(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in records:
        rows.append(
            {
                "id": _value(record, "pk", "id"),
                "part_id": _nested_id(_value(record, "part")),
                "quantity": _value(record, "quantity"),
                "location_id": _nested_id(_value(record, "location")),
                "status": _value(record, "status"),
                "batch": _value(record, "batch"),
            }
        )
    return rows


def _normalize_categories(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in records:
        rows.append(
            {
                "id": _value(record, "pk", "id"),
                "name": _value(record, "name"),
                "parent_id": _nested_id(_value(record, "parent")),
                "description": _value(record, "description"),
            }
        )
    return rows


def _normalize_companies(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in records:
        rows.append(
            {
                "id": _value(record, "pk", "id"),
                "name": _value(record, "name"),
                "is_supplier": _value(record, "is_supplier"),
                "is_manufacturer": _value(record, "is_manufacturer"),
                "is_customer": _value(record, "is_customer"),
            }
        )
    return rows


NORMALIZERS = {
    "parts": (
        _normalize_parts,
        ["id", "name", "description", "ipn", "category_id", "active", "virtual"],
    ),
    "stock_records": (
        _normalize_stock,
        ["id", "part_id", "quantity", "location_id", "status", "batch"],
    ),
    "categories": (
        _normalize_categories,
        ["id", "name", "parent_id", "description"],
    ),
    "companies": (
        _normalize_companies,
        ["id", "name", "is_supplier", "is_manufacturer", "is_customer"],
    ),
}


async def ingest_inventree(
    *,
    client: InvenTreeClient,
    data_dir: Path,
) -> IngestionResult:
    """Fetch InvenTree inventory data and persist raw + processed snapshots."""

    timestamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    raw_dir = data_dir / "raw" / "inventree" / timestamp
    processed_dir = data_dir / "processed"

    snapshots = await client.fetch_inventory_snapshots()
    raw_counts: dict[str, int] = {}
    processed_files: dict[str, Path] = {}

    for snapshot in snapshots:
        raw_counts[snapshot.name] = len(snapshot.records)
        _write_jsonl(raw_dir / f"{snapshot.name}.jsonl", snapshot.records)

        normalizer, fieldnames = NORMALIZERS[snapshot.name]
        rows = normalizer(snapshot.records)
        path = processed_dir / f"{snapshot.name}.csv"
        _write_csv(path, fieldnames, rows)
        processed_files[snapshot.name] = path

    return IngestionResult(
        raw_dir=raw_dir,
        processed_dir=processed_dir,
        raw_counts=raw_counts,
        processed_files=processed_files,
    )


def data_summary(data_dir: Path) -> dict[str, Any]:
    """Return a small summary of local raw and processed inventory artifacts."""

    raw_root = data_dir / "raw" / "inventree"
    processed_root = data_dir / "processed"
    raw_snapshots = sorted(
        [path.name for path in raw_root.iterdir() if path.is_dir()]
        if raw_root.exists()
        else []
    )
    processed_files = sorted(
        [path.name for path in processed_root.glob("*.csv")]
        if processed_root.exists()
        else []
    )
    return {
        "raw_snapshot_count": len(raw_snapshots),
        "latest_raw_snapshot": raw_snapshots[-1] if raw_snapshots else None,
        "processed_files": processed_files,
    }

