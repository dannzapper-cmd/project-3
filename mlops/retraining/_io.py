"""Shared serialization / environment helpers for the retraining pipeline.

Kept tiny and dependency-light so it can be imported by the pure-logic modules
(gate, summary, rollback) without pulling in ZenML, MLflow, or pandas.
"""

from __future__ import annotations

import json
import math
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def now_utc() -> str:
    """ISO-8601 UTC timestamp."""

    return datetime.now(timezone.utc).isoformat()


def git_commit() -> str | None:
    """Best-effort short git commit hash for audit trails; ``None`` if unknown."""

    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    commit = result.stdout.strip()
    return commit or None


def is_finite_number(value: Any) -> bool:
    """True only for real, finite numeric values (not bool, NaN, or inf)."""

    if isinstance(value, bool):
        return False
    if not isinstance(value, (int, float)):
        return False
    return math.isfinite(float(value))


def json_default(value: Any) -> Any:
    """JSON encoder for numpy scalars, Paths, and datetimes (matches PR-05)."""

    # Imported lazily so the pure modules do not hard-depend on numpy/pandas.
    try:
        import numpy as np

        if isinstance(value, np.integer):
            return int(value)
        if isinstance(value, np.floating):
            return float(value)
        if isinstance(value, np.ndarray):
            return value.tolist()
    except ImportError:  # pragma: no cover - numpy always present in ml group
        pass
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def write_json(path: Path, payload: dict[str, Any]) -> Path:
    """Write ``payload`` to ``path`` deterministically (sorted keys)."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=json_default),
        encoding="utf-8",
    )
    return path


def read_json(path: Path) -> dict[str, Any]:
    """Read a JSON object from ``path``."""

    return json.loads(path.read_text(encoding="utf-8"))
