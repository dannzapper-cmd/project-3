"""Orchestrates audit logging, risk scoring, and anomaly detection."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from security.anomaly import AnomalyDetector
from security.audit import AuditLogger
from security.constants import (
    ANOMALY_CONTAMINATION,
    FORBIDDEN_ARTIFACT_SUBSTRINGS,
    OPS_HOURS_END,
    OPS_HOURS_START,
    POSTURE_CLEAN_ANOMALY_RATE_MAX,
    POSTURE_HIGH_RISK_ANOMALY_RATE_MIN,
    RANDOM_STATE,
)
from security.risk_scorer import RiskScorer

DEFAULT_DATA_DIR = Path("data/synthetic/output")
DEFAULT_OUTPUT_DIR = Path("artifacts/security")
MOVEMENTS_FILE = "stock_movements.csv"


def _ensure_synthetic_data(data_dir: Path) -> Path:
    movements_path = data_dir / MOVEMENTS_FILE
    if movements_path.is_file():
        return movements_path

    repo_root = Path(__file__).resolve().parents[1]
    makefile = repo_root / "Makefile"
    if makefile.is_file():
        result = subprocess.run(
            ["make", "generate-data"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0 and movements_path.is_file():
            return movements_path

    msg = (
        f"Required input not found: {movements_path}. "
        "Run 'make generate-data' first."
    )
    raise FileNotFoundError(msg)


def _load_movements(data_dir: Path) -> pd.DataFrame:
    path = _ensure_synthetic_data(data_dir)
    return pd.read_csv(path)


def _scan_for_secrets(text: str) -> list[str]:
    lowered = text.lower()
    return [token for token in FORBIDDEN_ARTIFACT_SUBSTRINGS if token in lowered]


def _validate_artifacts_safe(*paths: Path) -> None:
    for path in paths:
        if not path.exists():
            continue
        content = path.read_text(encoding="utf-8").lower()
        hits = _scan_for_secrets(content)
        if hits:
            raise ValueError(
                f"Artifact {path} may contain sensitive patterns: {hits}"
            )


def _compute_posture(
    anomaly_rate: float,
    high_risk_events: int,
    critical_risk_events: int,
) -> tuple[str, str]:
    if (
        anomaly_rate >= POSTURE_HIGH_RISK_ANOMALY_RATE_MIN
        or critical_risk_events > 0
    ):
        return (
            "HIGH_RISK",
            "Elevated anomaly rate or critical risk indicators require review.",
        )
    if anomaly_rate >= POSTURE_CLEAN_ANOMALY_RATE_MAX or high_risk_events > 0:
        return (
            "ELEVATED",
            "Anomaly rate or high-risk events exceed clean thresholds.",
        )
    return ("CLEAN", "No high-risk or critical events; anomaly rate within bounds.")


def _log_after_hours_events(
    movements: pd.DataFrame, audit: AuditLogger
) -> None:
    """Mark movements outside configured ops hours for human review (not malicious)."""
    for _, row in movements.iterrows():
        event_dt = pd.to_datetime(row["date"])
        hour = event_dt.hour
        if hour < OPS_HOURS_START or hour >= OPS_HOURS_END:
            audit.log(
                event_type="STOCK_MOVEMENT",
                severity="INFO",
                actor="batch_job",
                part_id=str(row["part_id"]),
                movement_id=str(row["movement_id"]),
                description=(
                    "Event recorded outside configured operational hours "
                    f"(default {OPS_HOURS_START:02d}:00-{OPS_HOURS_END:02d}:00 UTC). "
                    "Marked for review, not as confirmation of malicious activity."
                ),
            )


def run_security_pipeline(
    output_dir: Path,
    data_dir: Path | None = None,
) -> dict[str, Path]:
    """Run the full defensive security pipeline and write artifacts."""
    data_path = data_dir or DEFAULT_DATA_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    movements = _load_movements(data_path)
    audit = AuditLogger(output_dir / "audit_log.jsonl")

    audit.log(
        event_type="SYSTEM_CHECK",
        severity="INFO",
        actor="system",
        description=f"Security pipeline started; analyzing {len(movements)} movements.",
    )

    _log_after_hours_events(movements, audit)

    risk_scorer = RiskScorer(movements)
    risk_results = risk_scorer.score_all()

    for item in risk_results:
        severity = "INFO"
        if item["risk_level"] == "HIGH":
            severity = "WARNING"
        elif item["risk_level"] == "CRITICAL":
            severity = "CRITICAL"
        audit.log(
            event_type="RISK_SCORE_GENERATED",
            severity=severity,  # type: ignore[arg-type]
            actor="system",
            part_id=item["part_id"],
            movement_id=item["event_id"],
            description=f"Risk score {item['risk_score']:.2f} ({item['risk_level']}).",
            metadata={"factors": item["factors"][:5]},
        )

    detector = AnomalyDetector(movements, audit=audit)
    for part_id in detector.insufficient_zscore_parts:
        audit.log(
            event_type="DATA_QUALITY_ISSUE",
            severity="INFO",
            actor="system",
            part_id=part_id,
            description=(
                "quantity_zscore_per_part set to 0.0 due to fewer than 3 observations."
            ),
        )

    anomaly_df = detector.detect()
    for _, row in anomaly_df[anomaly_df["is_anomaly"] == 1].iterrows():
        audit.log(
            event_type="ANOMALY_DETECTED",
            severity="WARNING",
            actor="system",
            part_id=str(row["part_id"]),
            movement_id=str(row["movement_id"]),
            description=(
                f"Anomaly indicator score {float(row['anomaly_score']):.4f} "
                f"for movement {row['movement_id']}."
            ),
        )

    risk_path = output_dir / "risk_score_summary.json"
    with risk_path.open("w", encoding="utf-8") as handle:
        json.dump(risk_results, handle, indent=2)

    anomaly_path = output_dir / "anomaly_results.csv"
    anomaly_df.to_csv(anomaly_path, index=False)

    dates = pd.to_datetime(movements["date"])
    period_start = dates.min().strftime("%Y-%m-%d")
    period_end = dates.max().strftime("%Y-%m-%d")

    total = len(movements)
    total_anomalies = int(anomaly_df["is_anomaly"].sum())
    anomaly_rate = total_anomalies / total if total else 0.0

    high_risk = sum(1 for r in risk_results if r["risk_level"] == "HIGH")
    critical_risk = sum(1 for r in risk_results if r["risk_level"] == "CRITICAL")

    part_risk = Counter(
        r["part_id"] for r in risk_results if r["risk_level"] in ("HIGH", "CRITICAL")
    )
    top_risk_parts = [pid for pid, _ in part_risk.most_common(10)]

    posture, posture_reason = _compute_posture(
        anomaly_rate, high_risk, critical_risk
    )

    summary: dict[str, Any] = {
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "period_analyzed": {"start": period_start, "end": period_end},
        "total_events_analyzed": total,
        "total_anomalies_detected": total_anomalies,
        "high_risk_events": high_risk,
        "critical_risk_events": critical_risk,
        "top_risk_parts": top_risk_parts,
        "anomaly_rate": round(anomaly_rate, 6),
        "audit_log_path": "artifacts/security/audit_log.jsonl",
        "model_used": "IsolationForest",
        "contamination_param": ANOMALY_CONTAMINATION,
        "random_state": RANDOM_STATE,
        "posture": posture,
        "posture_reason": posture_reason,
    }

    summary_path = output_dir / "security_summary.json"
    with summary_path.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)

    audit_path = audit.flush()

    _validate_artifacts_safe(
        audit_path,
        risk_path,
        anomaly_path,
        summary_path,
    )

    return {
        "audit_log": audit_path,
        "risk_score_summary": risk_path,
        "anomaly_results": anomaly_path,
        "security_summary": summary_path,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="InvForge defensive security pipeline")
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for security artifacts",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="Directory containing stock_movements.csv",
    )
    args = parser.parse_args(argv)

    try:
        paths = run_security_pipeline(
            output_dir=args.output,
            data_dir=args.data_dir,
        )
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    for name, path in paths.items():
        print(f"Wrote {name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
