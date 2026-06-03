"""Audit log generation for inventory and security-relevant events."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from security.constants import AUDIT_DESCRIPTION_MAX_LEN

AuditEventType = Literal[
    "STOCK_MOVEMENT",
    "ANOMALY_DETECTED",
    "RISK_SCORE_GENERATED",
    "SYSTEM_CHECK",
    "DATA_QUALITY_ISSUE",
]
AuditSeverity = Literal["INFO", "WARNING", "HIGH", "CRITICAL"]
AuditActor = Literal["system", "api", "batch_job"]


class AuditLogger:
    """Writes defensive audit events as JSONL with a fixed schema."""

    def __init__(self, output_path: Path) -> None:
        self._path = output_path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._events: list[dict[str, Any]] = []

    def log(
        self,
        *,
        event_type: AuditEventType,
        severity: AuditSeverity,
        actor: AuditActor,
        description: str,
        part_id: str | None = None,
        movement_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        timestamp: datetime | None = None,
    ) -> dict[str, Any]:
        """Record one audit event (in memory until flush)."""
        desc = description[:AUDIT_DESCRIPTION_MAX_LEN]
        event = {
            "timestamp": (timestamp or datetime.now(UTC)).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
            "event_type": event_type,
            "severity": severity,
            "actor": actor,
            "part_id": part_id,
            "movement_id": movement_id,
            "description": desc,
            "metadata": metadata if metadata is not None else {},
        }
        self._events.append(event)
        return event

    @property
    def events(self) -> list[dict[str, Any]]:
        return list(self._events)

    @property
    def path(self) -> Path:
        return self._path

    def flush(self) -> Path:
        """Write all buffered events to the JSONL file."""
        with self._path.open("w", encoding="utf-8") as handle:
            for event in self._events:
                handle.write(json.dumps(event, separators=(",", ":")) + "\n")
        return self._path
