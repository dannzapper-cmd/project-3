"""Fast offline validation of generated security artifacts (no pytest)."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

REQUIRED_SUMMARY_KEYS = {
    "generated_at",
    "posture",
    "total_events_analyzed",
    "anomaly_rate",
    "audit_log_path",
}

REQUIRED_AUDIT_KEYS = {
    "timestamp",
    "event_type",
    "severity",
    "actor",
    "part_id",
    "movement_id",
    "description",
    "metadata",
}


def _fail(message: str) -> None:
    print(f"SMOKE FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def validate_artifacts(artifacts_dir: Path) -> None:
    audit_path = artifacts_dir / "audit_log.jsonl"
    if not audit_path.is_file():
        _fail(f"missing {audit_path}")

    text = audit_path.read_text(encoding="utf-8")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        _fail("audit_log.jsonl has no events")

    for line in lines[:5]:
        event = json.loads(line)
        missing = REQUIRED_AUDIT_KEYS - set(event.keys())
        if missing:
            _fail(f"audit event missing keys: {missing}")

    risk_path = artifacts_dir / "risk_score_summary.json"
    if not risk_path.is_file():
        _fail(f"missing {risk_path}")
    risk_data = json.loads(risk_path.read_text(encoding="utf-8"))
    if not isinstance(risk_data, list):
        _fail("risk_score_summary.json must be a JSON array")

    summary_path = artifacts_dir / "security_summary.json"
    if not summary_path.is_file():
        _fail(f"missing {summary_path}")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    missing_summary = REQUIRED_SUMMARY_KEYS - set(summary.keys())
    if missing_summary:
        _fail(f"security_summary missing keys: {missing_summary}")

    anomaly_path = artifacts_dir / "anomaly_results.csv"
    if not anomaly_path.is_file():
        _fail(f"missing {anomaly_path}")
    with anomaly_path.open(encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or "is_anomaly" not in reader.fieldnames:
            _fail("anomaly_results.csv missing is_anomaly column")

    print(f"Security smoke check passed ({artifacts_dir})")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="InvForge security artifact smoke check",
    )
    parser.add_argument(
        "--artifacts-dir",
        type=Path,
        default=Path("artifacts/security"),
    )
    args = parser.parse_args(argv)
    try:
        validate_artifacts(args.artifacts_dir)
    except SystemExit:
        raise
    except Exception as exc:
        _fail(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
