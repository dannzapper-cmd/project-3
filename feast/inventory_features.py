"""Minimal Feast definitions for future InvForge demand and stock features."""

from __future__ import annotations

from datetime import timedelta

from feast import Entity, FeatureView, Field, FileSource, ValueType
from feast.types import Float32, Int64, String

part = Entity(
    name="part",
    join_keys=["part_id"],
    value_type=ValueType.STRING,
    description="Inventory part/item identifier from InvenTree or synthetic data.",
)

demand_history_source = FileSource(
    name="synthetic_demand_history",
    path="../data/synthetic/output/demand_history.csv",
    timestamp_field="date",
    description="Synthetic daily demand history generated locally.",
)

processed_stock_source = FileSource(
    name="processed_stock_records",
    path="../data/processed/stock_records.csv",
    timestamp_field="event_timestamp",
    description=(
        "Future stock feature source derived from read-only InvenTree ingestion."
    ),
)

demand_history_features = FeatureView(
    name="demand_history_features",
    entities=[part],
    ttl=timedelta(days=730),
    schema=[
        Field(name="quantity_demand", dtype=Float32),
        Field(name="stockout_flag", dtype=Int64),
        Field(name="demand_pattern", dtype=String),
    ],
    source=demand_history_source,
    online=False,
    description="Foundation for future demand forecasting features.",
)

stock_level_features = FeatureView(
    name="stock_level_features",
    entities=[part],
    ttl=timedelta(days=30),
    schema=[
        Field(name="quantity", dtype=Float32),
        Field(name="location_id", dtype=String),
        Field(name="status", dtype=String),
    ],
    source=processed_stock_source,
    online=False,
    description="Foundation for future stock availability features.",
)

