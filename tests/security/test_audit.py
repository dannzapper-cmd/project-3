"""Audit log schema and secret-safety tests."""

from __future__ import annotations

import json
from pathlib import Path

from security.audit import AuditLogger
from security.constants import FORBIDDEN_ARTIFACT_SUBSTRINGS

REQUIRED_KEYS = {
    "timestamp",
    "event_type",
    "severity",
    "actor",
    "part_id",
    "movement_id",
    "description",
    "metadata",
}


def test_audit_event_schema(tmp_path: Path) -> None:
    logger = AuditLogger(tmp_path / "audit_log.jsonl")
    event = logger.log(
        event_type="SYSTEM_CHECK",
        severity="INFO",
        actor="system",
        description="Defensive check completed.",
        part_id="PART-001",
        movement_id="MOV-000001",
    )
    assert set(event.keys()) == REQUIRED_KEYS
    assert event["metadata"] == {}
    logger.flush()
    line = (tmp_path / "audit_log.jsonl").read_text(encoding="utf-8").strip()
    parsed = json.loads(line)
    assert set(parsed.keys()) == REQUIRED_KEYS


def test_audit_description_truncated(tmp_path: Path) -> None:
    logger = AuditLogger(tmp_path / "audit_log.jsonl")
    long_desc = "x" * 300
    event = logger.log(
        event_type="SYSTEM_CHECK",
        severity="INFO",
        actor="system",
        description=long_desc,
    )
    assert len(event["description"]) <= 200


def test_audit_output_has_no_secret_patterns(tmp_path: Path) -> None:
    logger = AuditLogger(tmp_path / "audit_log.jsonl")
    logger.log(
        event_type="SYSTEM_CHECK",
        severity="INFO",
        actor="system",
        description="Pipeline run without credentials.",
    )
    path = logger.flush()
    content = path.read_text(encoding="utf-8").lower()
    for token in FORBIDDEN_ARTIFACT_SUBSTRINGS:
        assert token not in content
