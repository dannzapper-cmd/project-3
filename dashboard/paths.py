"""Default artifact paths for the PR-06 dashboard."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_SYNTHETIC_DIR = REPO_ROOT / "data" / "synthetic" / "output"
DEFAULT_DECISION_DIR = REPO_ROOT / "artifacts" / "decision"
DEFAULT_MLOPS_DIR = REPO_ROOT / "artifacts" / "mlops"

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

MLRUNS_DIR = REPO_ROOT / "mlruns"
RETRAINING_DIR = REPO_ROOT / "artifacts" / "retraining"
DEFAULT_PROCESSED_DIR = REPO_ROOT / "data" / "processed"
