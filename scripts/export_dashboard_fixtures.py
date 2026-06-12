#!/usr/bin/env python3
"""Export lightweight dashboard demo fixtures from a local pipeline run.

Copies truncated synthetic CSVs and small JSON/CSV artifacts into
``dashboard/demo_fixtures/`` for Cloud Run bundling. Safe to run offline
after ``make demo-local``.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FIXTURES = REPO / "dashboard" / "demo_fixtures"
ARTIFACTS = REPO / "artifacts"
SYNTHETIC = REPO / "data" / "synthetic" / "output"

CSV_HEAD_ROWS = {
    "parts.csv": 21,
    "stock_movements.csv": 21,
    "demand_history.csv": 51,
}

COPY_FILES = [
    (ARTIFACTS / "decision" / "decision_summary.json", "decision"),
    (ARTIFACTS / "decision" / "decision_recommendations.csv", "decision"),
    (ARTIFACTS / "mlops" / "mlops_loop_summary.json", "mlops"),
    (
        ARTIFACTS / "mlops" / "champion_challenger" / "comparison.json",
        "mlops/champion_challenger",
    ),
    (
        ARTIFACTS / "mlops" / "registry" / "registered_model_summary.json",
        "mlops/registry",
    ),
    (
        ARTIFACTS / "mlops" / "bentoml" / "build_summary.json",
        "mlops/bentoml",
    ),
    (
        ARTIFACTS / "mlops" / "evidently" / "data_drift_report.json",
        "mlops/evidently",
    ),
    (
        ARTIFACTS / "mlops" / "evidently" / "data_quality_report.json",
        "mlops/evidently",
    ),
]


def _truncate_csv(src: Path, dest: Path, max_rows: int) -> None:
    lines = src.read_text(encoding="utf-8").splitlines()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("\n".join(lines[:max_rows]) + "\n", encoding="utf-8")


def main() -> int:
    if not ARTIFACTS.is_dir():
        print(
            "ERROR: run `make demo-local` first (artifacts/ missing)",
            file=sys.stderr,
        )
        return 1
    if not SYNTHETIC.is_dir():
        print(
            "ERROR: synthetic output missing; run `make generate-data`",
            file=sys.stderr,
        )
        return 1

    for name, max_rows in CSV_HEAD_ROWS.items():
        src = SYNTHETIC / name
        if not src.is_file():
            print(f"ERROR: missing {src}", file=sys.stderr)
            return 1
        _truncate_csv(src, FIXTURES / "synthetic" / "output" / name, max_rows)

    for src, rel in COPY_FILES:
        if not src.is_file():
            print(f"ERROR: missing {src}", file=sys.stderr)
            return 1
        dest = FIXTURES / rel / src.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)

    print(f"Exported dashboard fixtures to {FIXTURES}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
