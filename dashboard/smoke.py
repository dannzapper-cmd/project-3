"""Non-interactive smoke checks for PR-06 dashboard loaders.

Validates loader contracts against real and missing paths without Streamlit.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable

from dashboard import loaders
from dashboard.paths import REPO_ROOT
from dashboard.types import LoaderResult

LOADER_CALLS: list[tuple[str, Callable[..., LoaderResult]]] = [
    ("load_synthetic_data_status", loaders.load_synthetic_data_status),
    ("load_decision_summary", loaders.load_decision_summary),
    ("load_decision_recommendations", loaders.load_decision_recommendations),
    (
        "load_champion_challenger_comparison",
        loaders.load_champion_challenger_comparison,
    ),
    ("load_mlops_loop_summary", loaders.load_mlops_loop_summary),
    ("load_registry_summary", loaders.load_registry_summary),
    ("load_bentoml_build_summary", loaders.load_bentoml_build_summary),
    ("load_evidently_artifact_status", loaders.load_evidently_artifact_status),
]


def _validate_result(name: str, result: object) -> None:
    if not isinstance(result, dict):
        raise TypeError(f"{name}: expected dict, got {type(result).__name__}")
    status = result.get("status")
    if status not in {"ok", "missing"}:
        raise ValueError(f"{name}: invalid status {status!r}")
    if status == "ok":
        if "data" not in result or "mtime" not in result:
            raise ValueError(f"{name}: ok result missing data/mtime keys")
    else:
        if "reason" not in result or "commands" not in result:
            raise ValueError(f"{name}: missing result missing reason/commands")


def _missing_path_args(name: str) -> dict:
    missing = Path("/nonexistent/invforge-pr06-smoke")
    if name == "load_synthetic_data_status":
        return {"synthetic_dir": missing}
    if name == "load_evidently_artifact_status":
        return {
            "drift_path": missing / "drift.json",
            "quality_path": missing / "quality.json",
        }
    return {"path": missing / f"{name}.json"}


def main() -> int:
    artifacts_root = REPO_ROOT / "artifacts"
    print(f"Smoke: real artifacts dir exists={artifacts_root.is_dir()}")

    for name, fn in LOADER_CALLS:
        result = fn()
        _validate_result(name, result)
        print(f"  {name} (real): {result['status']}")

        missing_kwargs = _missing_path_args(name)
        missing_result = fn(**missing_kwargs)
        _validate_result(name, missing_result)
        if missing_result["status"] != "missing":
            raise AssertionError(f"{name}: expected missing for bogus path")

    print("Dashboard smoke: all loader contract checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
