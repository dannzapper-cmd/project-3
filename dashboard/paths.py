"""Default artifact paths for the PR-06 dashboard."""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _fixtures_root() -> Path | None:
    raw = os.getenv("INVFORGE_DASHBOARD_FIXTURES_DIR", "").strip()
    if raw:
        return Path(raw)
    env = os.getenv("INVFORGE_ENV", "local").strip().lower()
    if env in {"demo", "cloud"}:
        return Path(__file__).resolve().parent / "demo_fixtures"
    return None


def _artifact_root(name: str, default: Path) -> Path:
    root = _fixtures_root()
    if root is None:
        return default
    return root / name


DEFAULT_SYNTHETIC_DIR = _artifact_root(
    "synthetic/output", REPO_ROOT / "data" / "synthetic" / "output"
)
DEFAULT_DECISION_DIR = _artifact_root(
    "decision", REPO_ROOT / "artifacts" / "decision"
)
DEFAULT_MLOPS_DIR = _artifact_root(
    "mlops", REPO_ROOT / "artifacts" / "mlops"
)

DECISION_SUMMARY = DEFAULT_DECISION_DIR / "decision_summary.json"
DECISION_RECOMMENDATIONS = DEFAULT_DECISION_DIR / "decision_recommendations.csv"
MLOPS_LOOP_SUMMARY = DEFAULT_MLOPS_DIR / "mlops_loop_summary.json"
REGISTRY_SUMMARY = DEFAULT_MLOPS_DIR / "registry" / "registered_model_summary.json"
CHAMPION_CHALLENGER = DEFAULT_MLOPS_DIR / "champion_challenger" / "comparison.json"
BENTOML_BUILD_SUMMARY = DEFAULT_MLOPS_DIR / "bentoml" / "build_summary.json"
EVIDENTLY_DRIFT_JSON = DEFAULT_MLOPS_DIR / "evidently" / "data_drift_report.json"
EVIDENTLY_QUALITY_JSON = DEFAULT_MLOPS_DIR / "evidently" / "data_quality_report.json"

SYNTHETIC_MARKERS = (
    "demand_history.csv",
    "parts.csv",
    "stock_movements.csv",
)

CMD_GENERATE_DATA = 'make UV="uv" generate-data'
CMD_TRAIN_ML = 'make UV="uv" train-ml'
CMD_DECISION_INTEL = 'make UV="uv" decision-intel'
CMD_MLOPS_LOOP = 'make UV="uv" mlops-loop'
CMD_DEMO_LOCAL = 'make UV="uv" demo-local'
CMD_REVIEWER_DEMO = 'make UV="uv" reviewer-demo'
