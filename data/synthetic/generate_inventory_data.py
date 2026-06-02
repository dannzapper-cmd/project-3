#!/usr/bin/env python3
"""Deterministic synthetic inventory dataset generator for InvForge.

Generates CSV files suitable for future ML pipelines (PR-03+) without
requiring ML libraries. Uses Python standard library only.

Output files:
  - categories.csv
  - suppliers.csv
  - parts.csv
  - stock_movements.csv
  - demand_history.csv
"""

from __future__ import annotations

import argparse
import csv
import random
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

# --- Configuration defaults (deterministic when seed is fixed) ---

NUM_CATEGORIES = 12
NUM_SUPPLIERS = 8
NUM_PARTS = 120
HISTORY_DAYS = 365
INTERMITTENT_FRACTION = 0.30  # ~30% sparse/zero-heavy demand for ADI/CV² work

CATEGORY_NAMES = [
    "Fasteners",
    "Electronics",
    "Mechanical",
    "Raw Materials",
    "Packaging",
    "Tools",
    "Safety",
    "Hydraulics",
    "Pneumatics",
    "Consumables",
    "Assemblies",
    "Spare Parts",
]

SUPPLIER_NAMES = [
    "Northline Industrial Supply",
    "Global Parts Co.",
    "Precision Components Ltd.",
    "Atlas Manufacturing",
    "Summit Electronics",
    "Harbor Logistics",
    "Vertex Materials",
    "Continental MRO",
]

PART_PREFIXES = [
    "BOLT",
    "NUT",
    "RES",
    "CAP",
    "BRG",
    "SHAFT",
    "VALVE",
    "HOSE",
    "GASKET",
    "PCB",
    "MTR",
    "SENS",
]

PART_SUFFIXES = [
    "A",
    "B",
    "C",
    "X",
    "Pro",
    "Lite",
    "HD",
    "SS",
    "V2",
    "XL",
]


@dataclass(frozen=True)
class Category:
    category_id: str
    name: str
    parent_id: str
    description: str


@dataclass(frozen=True)
class Supplier:
    supplier_id: str
    name: str
    country: str
    lead_time_days: int
    reliability_score: float


@dataclass(frozen=True)
class Part:
    part_id: str
    sku: str
    name: str
    category_id: str
    supplier_id: str
    unit_cost: float
    reorder_point: float
    safety_stock: float
    lead_time_days: int
    current_stock: float
    stockout_flag: bool
    demand_pattern: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate deterministic synthetic inventory CSV datasets."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/synthetic/output"),
        help="Output directory for CSV files",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for deterministic output",
    )
    return parser.parse_args()


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def generate_categories(rng: random.Random) -> list[Category]:
    categories: list[Category] = []
    for idx, name in enumerate(CATEGORY_NAMES[:NUM_CATEGORIES], start=1):
        parent = "" if idx <= 4 else f"CAT-{rng.randint(1, 4):03d}"
        categories.append(
            Category(
                category_id=f"CAT-{idx:03d}",
                name=name,
                parent_id=parent,
                description=f"{name} inventory category",
            )
        )
    return categories


def generate_suppliers(rng: random.Random) -> list[Supplier]:
    countries = ["US", "DE", "CN", "MX", "JP", "CA", "PL", "IN"]
    suppliers: list[Supplier] = []
    for idx, name in enumerate(SUPPLIER_NAMES[:NUM_SUPPLIERS], start=1):
        suppliers.append(
            Supplier(
                supplier_id=f"SUP-{idx:03d}",
                name=name,
                country=countries[(idx - 1) % len(countries)],
                lead_time_days=rng.randint(3, 28),
                reliability_score=round(rng.uniform(0.75, 0.99), 3),
            )
        )
    return suppliers


def generate_parts(
    rng: random.Random,
    categories: list[Category],
    suppliers: list[Supplier],
) -> list[Part]:
    intermittent_count = int(NUM_PARTS * INTERMITTENT_FRACTION)
    intermittent_indices = set(
        rng.sample(range(NUM_PARTS), k=intermittent_count)
    )

    parts: list[Part] = []
    for idx in range(NUM_PARTS):
        part_num = idx + 1
        prefix = PART_PREFIXES[idx % len(PART_PREFIXES)]
        suffix = PART_SUFFIXES[rng.randint(0, len(PART_SUFFIXES) - 1)]
        sku = f"{prefix}-{part_num:04d}-{suffix}"
        name = f"{prefix} Component {part_num}"
        category = categories[rng.randint(0, len(categories) - 1)]
        supplier = suppliers[rng.randint(0, len(suppliers) - 1)]
        unit_cost = round(rng.uniform(0.45, 850.0), 2)
        lead_time = supplier.lead_time_days + rng.randint(-2, 5)
        lead_time = max(1, lead_time)

        is_intermittent = idx in intermittent_indices
        demand_pattern = "intermittent" if is_intermittent else "regular"

        if is_intermittent:
            avg_demand = rng.uniform(0.05, 1.2)
            safety_stock = round(avg_demand * lead_time * rng.uniform(1.5, 3.0), 2)
            reorder_point = round(avg_demand * lead_time + safety_stock, 2)
            current_stock = round(rng.uniform(0, reorder_point * 1.5), 2)
        else:
            avg_demand = rng.uniform(2.0, 45.0)
            safety_stock = round(
                avg_demand * (lead_time**0.5) * rng.uniform(0.8, 1.6),
                2,
            )
            reorder_point = round(avg_demand * lead_time + safety_stock, 2)
            current_stock = round(
                rng.uniform(reorder_point * 0.2, reorder_point * 2.5),
                2,
            )

        stockout_flag = current_stock <= safety_stock * 0.5

        parts.append(
            Part(
                part_id=f"PRT-{part_num:04d}",
                sku=sku,
                name=name,
                category_id=category.category_id,
                supplier_id=supplier.supplier_id,
                unit_cost=unit_cost,
                reorder_point=reorder_point,
                safety_stock=safety_stock,
                lead_time_days=lead_time,
                current_stock=current_stock,
                stockout_flag=stockout_flag,
                demand_pattern=demand_pattern,
            )
        )
    return parts


def generate_demand_history(
    rng: random.Random,
    parts: list[Part],
    start: date,
    days: int,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for part in parts:
        for offset in range(days):
            current_date = start + timedelta(days=offset)
            weekday = current_date.weekday()

            if part.demand_pattern == "intermittent":
                # Sparse demand: many zero days, occasional bursts
                if rng.random() < 0.82:
                    quantity = 0.0
                elif rng.random() < 0.12:
                    quantity = float(rng.randint(1, 3))
                else:
                    quantity = float(rng.randint(4, 18))
            else:
                base = max(1.0, part.reorder_point / max(part.lead_time_days, 1) / 5)
                seasonality = 1.0 + 0.25 * (1 if weekday < 5 else -0.3)
                noise = rng.uniform(0.6, 1.4)
                trend = 1.0 + (offset / days) * rng.uniform(-0.1, 0.15)
                quantity = max(0.0, round(base * seasonality * noise * trend, 2))

            stockout = quantity > 0 and rng.random() < (
                0.18 if part.demand_pattern == "intermittent" else 0.06
            )

            rows.append(
                {
                    "part_id": part.part_id,
                    "date": current_date.isoformat(),
                    "quantity_demand": quantity,
                    "stockout_flag": int(stockout),
                    "demand_pattern": part.demand_pattern,
                }
            )
    return rows


def generate_stock_movements(
    rng: random.Random,
    parts: list[Part],
    start: date,
    days: int,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    movement_id = 1

    for part in parts:
        # Initial stock receipt
        rows.append(
            {
                "movement_id": f"MOV-{movement_id:06d}",
                "part_id": part.part_id,
                "date": start.isoformat(),
                "movement_type": "in",
                "quantity": round(part.current_stock * rng.uniform(1.1, 2.0), 2),
                "reference": "INIT-RECEIPT",
            }
        )
        movement_id += 1

        # Periodic movements across the history window
        num_events = rng.randint(8, 24)
        for _ in range(num_events):
            event_date = start + timedelta(days=rng.randint(0, days - 1))
            if rng.random() < 0.45:
                movement_type = "in"
                quantity = round(rng.uniform(5, 120), 2)
                reference = f"PO-{rng.randint(1000, 9999)}"
            elif rng.random() < 0.85:
                movement_type = "out"
                quantity = round(rng.uniform(1, 40), 2)
                reference = f"SO-{rng.randint(1000, 9999)}"
            else:
                movement_type = "adjustment"
                quantity = round(rng.uniform(-5, 5), 2)
                reference = "CYCLE-COUNT"

            rows.append(
                {
                    "movement_id": f"MOV-{movement_id:06d}",
                    "part_id": part.part_id,
                    "date": event_date.isoformat(),
                    "movement_type": movement_type,
                    "quantity": quantity,
                    "reference": reference,
                }
            )
            movement_id += 1

    rows.sort(key=lambda row: (row["part_id"], row["date"], row["movement_id"]))
    return rows


def main() -> None:
    args = parse_args()
    rng = random.Random(args.seed)

    start_date = date(2024, 1, 1)

    categories = generate_categories(rng)
    suppliers = generate_suppliers(rng)
    parts = generate_parts(rng, categories, suppliers)
    demand_history = generate_demand_history(rng, parts, start_date, HISTORY_DAYS)
    stock_movements = generate_stock_movements(rng, parts, start_date, HISTORY_DAYS)

    output_dir = args.output
    write_csv(
        output_dir / "categories.csv",
        ["category_id", "name", "parent_id", "description"],
        [
            {
                "category_id": c.category_id,
                "name": c.name,
                "parent_id": c.parent_id,
                "description": c.description,
            }
            for c in categories
        ],
    )
    write_csv(
        output_dir / "suppliers.csv",
        [
            "supplier_id",
            "name",
            "country",
            "lead_time_days",
            "reliability_score",
        ],
        [
            {
                "supplier_id": s.supplier_id,
                "name": s.name,
                "country": s.country,
                "lead_time_days": s.lead_time_days,
                "reliability_score": s.reliability_score,
            }
            for s in suppliers
        ],
    )
    write_csv(
        output_dir / "parts.csv",
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
                "part_id": p.part_id,
                "sku": p.sku,
                "name": p.name,
                "category_id": p.category_id,
                "supplier_id": p.supplier_id,
                "unit_cost": p.unit_cost,
                "reorder_point": p.reorder_point,
                "safety_stock": p.safety_stock,
                "lead_time_days": p.lead_time_days,
                "current_stock": p.current_stock,
                "stockout_flag": int(p.stockout_flag),
                "demand_pattern": p.demand_pattern,
            }
            for p in parts
        ],
    )
    write_csv(
        output_dir / "demand_history.csv",
        [
            "part_id",
            "date",
            "quantity_demand",
            "stockout_flag",
            "demand_pattern",
        ],
        demand_history,
    )
    write_csv(
        output_dir / "stock_movements.csv",
        [
            "movement_id",
            "part_id",
            "date",
            "movement_type",
            "quantity",
            "reference",
        ],
        stock_movements,
    )

    intermittent = sum(1 for p in parts if p.demand_pattern == "intermittent")
    print(f"Generated synthetic inventory data in {output_dir}")
    print(f"  categories:       {len(categories)}")
    print(f"  suppliers:        {len(suppliers)}")
    print(f"  parts:            {len(parts)} ({intermittent} intermittent)")
    print(f"  demand_history:   {len(demand_history)} rows")
    print(f"  stock_movements:  {len(stock_movements)} rows")
    print(f"  seed:             {args.seed}")


if __name__ == "__main__":
    main()
