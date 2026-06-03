"""Rule-based risk scoring for inventory movement events."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

import pandas as pd

from security.constants import (
    NEGATIVE_THRESHOLD,
    REVERSAL_WINDOW,
    RISK_LEVEL_HIGH_MAX,
    RISK_LEVEL_LOW_MAX,
    RISK_LEVEL_MEDIUM_MAX,
    RULE_DATA_QUALITY_WEIGHT,
    RULE_EXTREME_NEGATIVE_WEIGHT,
    RULE_QUANTITY_SPIKE_WEIGHT,
    RULE_REPEATED_REVERSAL_WEIGHT,
    RULE_UNKNOWN_REFERENCE_WEIGHT,
    SPIKE_MULTIPLIER,
    VALID_MOVEMENT_TYPES,
)

RULE_QUANTITY_SPIKE = "RULE_QUANTITY_SPIKE"
RULE_EXTREME_NEGATIVE = "RULE_EXTREME_NEGATIVE"
RULE_REPEATED_REVERSAL = "RULE_REPEATED_REVERSAL"
RULE_UNKNOWN_REFERENCE = "RULE_UNKNOWN_REFERENCE"
RULE_DATA_QUALITY = "RULE_DATA_QUALITY"


def _risk_level(score: float) -> str:
    if score <= RISK_LEVEL_LOW_MAX:
        return "LOW"
    if score <= RISK_LEVEL_MEDIUM_MAX:
        return "MEDIUM"
    if score <= RISK_LEVEL_HIGH_MAX:
        return "HIGH"
    return "CRITICAL"


def _is_valid_reference(reference: Any) -> bool:
    if reference is None or (isinstance(reference, float) and pd.isna(reference)):
        return False
    ref = str(reference).strip()
    if not ref:
        return False
    if ref in ("CYCLE-COUNT", "INIT-RECEIPT"):
        return True
    if ref.startswith("PO-") or ref.startswith("SO-"):
        return bool(re.match(r"^(PO|SO)-\d{4,}$", ref))
    return False


def _parse_date(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


class RiskScorer:
    """Applies documented weighted rules to stock movement rows."""

    def __init__(self, movements: pd.DataFrame) -> None:
        self._df = movements.copy()
        self._part_std = self._compute_part_std()

    def _compute_part_std(self) -> dict[str, float]:
        stds: dict[str, float] = {}
        for part_id, group in self._df.groupby("part_id"):
            qty = group["quantity"].astype(float)
            std_val = float(qty.std()) if len(qty) > 1 else 0.0
            stds[str(part_id)] = std_val if std_val > 0 else 1e-6
        return stds

    def _count_movements_in_window(
        self, part_id: str, center_date: datetime, window_days: int
    ) -> int:
        mask = self._df["part_id"].astype(str) == part_id
        subset = self._df.loc[mask].copy()
        dates = pd.to_datetime(subset["date"])
        delta = (dates - pd.Timestamp(center_date)).dt.days.abs()
        return int((delta <= window_days).sum())

    def score_row(self, row: pd.Series) -> dict[str, Any]:
        movement_id = str(row["movement_id"])
        part_id = str(row["part_id"])
        raw_type = row["movement_type"]
        movement_type = str(raw_type) if pd.notna(raw_type) else ""
        quantity = float(row["quantity"])
        row_date = _parse_date(row["date"])
        reference = row.get("reference")

        factors: list[str] = []
        rules_triggered: list[str] = []
        score = 0.0
        primary_rule: str | None = None

        part_std = self._part_std.get(part_id, 1e-6)
        if quantity > SPIKE_MULTIPLIER * part_std:
            multiplier = quantity / part_std if part_std > 0 else quantity
            factors.append(f"Quantity spike: {multiplier:.1f}x above part average")
            score += RULE_QUANTITY_SPIKE_WEIGHT
            rules_triggered.append(RULE_QUANTITY_SPIKE)
            primary_rule = RULE_QUANTITY_SPIKE

        if movement_type == "adjustment" and quantity < 0:
            if abs(quantity) > NEGATIVE_THRESHOLD:
                factors.append(f"Extreme negative adjustment: {quantity}")
                score += RULE_EXTREME_NEGATIVE_WEIGHT
                rules_triggered.append(RULE_EXTREME_NEGATIVE)
                if primary_rule is None:
                    primary_rule = RULE_EXTREME_NEGATIVE

        count_in_window = self._count_movements_in_window(
            part_id, row_date, REVERSAL_WINDOW
        )
        if count_in_window >= 3:
            factors.append(
                f"Repeated movements on same part in {count_in_window} days"
            )
            score += RULE_REPEATED_REVERSAL_WEIGHT
            rules_triggered.append(RULE_REPEATED_REVERSAL)
            if primary_rule is None:
                primary_rule = RULE_REPEATED_REVERSAL

        if not _is_valid_reference(reference):
            ref_display = "" if pd.isna(reference) else str(reference)
            factors.append(f"Unrecognized or missing reference: {ref_display}")
            score += RULE_UNKNOWN_REFERENCE_WEIGHT
            rules_triggered.append(RULE_UNKNOWN_REFERENCE)
            if primary_rule is None:
                primary_rule = RULE_UNKNOWN_REFERENCE

        if movement_type not in VALID_MOVEMENT_TYPES:
            factors.append(f"Unexpected movement type: {movement_type}")
            score += RULE_DATA_QUALITY_WEIGHT
            rules_triggered.append(RULE_DATA_QUALITY)
            if primary_rule is None:
                primary_rule = RULE_DATA_QUALITY

        score = min(score, 1.0)
        if not factors:
            score = 0.0

        date_iso = (
            row_date.strftime("%Y-%m-%dT%H:%M:%SZ")
            if row_date.tzinfo
            else row_date.strftime("%Y-%m-%dT00:00:00Z")
        )

        return {
            "event_id": movement_id,
            "part_id": part_id,
            "date": date_iso,
            "movement_type": movement_type,
            "quantity": quantity,
            "risk_score": round(score, 4),
            "risk_level": _risk_level(score),
            "factors": factors,
            "rule_triggered": primary_rule,
        }

    def score_all(self) -> list[dict[str, Any]]:
        return [self.score_row(row) for _, row in self._df.iterrows()]
