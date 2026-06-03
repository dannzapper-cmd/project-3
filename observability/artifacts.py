"""Artifact specifications for PR-07 observability (paths + safe keys).

This module is intentionally dependency-light (stdlib only) so it can be
imported by the health builder, the metrics collectors, and the smoke test
without pulling in pandas, streamlit, or any ML/MLOps dependency group.

Only the low-cardinality, allowlisted artifact *keys* below are ever used as
metric label values or health status keys. Filenames and absolute paths are
never exposed.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Allowlisted artifact keys (B2 / B3). These are the ONLY values permitted as
# label values for invforge_artifact_available / invforge_artifact_age_seconds
# and as keys in the /health "artifacts" object.
ARTIFACT_KEYS: tuple[str, ...] = (
    "decision_summary",
    "decision_recommendations",
    "mlops_loop_summary",
    "registry_summary",
    "champion_challenger_comparison",
)


@dataclass(frozen=True)
class ArtifactSpec:
    """A single observable artifact.

    ``key`` is the safe, low-cardinality label/health key. ``path`` is the
    on-disk location and is NEVER exposed via metrics, health, or logs.
    """

    key: str
    path: Path


# Relative artifact locations (must match PR-04/PR-05/PR-06 writers).
_ARTIFACT_RELPATHS: dict[str, str] = {
    "decision_summary": "artifacts/decision/decision_summary.json",
    "decision_recommendations": "artifacts/decision/decision_recommendations.csv",
    "mlops_loop_summary": "artifacts/mlops/mlops_loop_summary.json",
    "registry_summary": "artifacts/mlops/registry/registered_model_summary.json",
    "champion_challenger_comparison": (
        "artifacts/mlops/champion_challenger/comparison.json"
    ),
}

# Additional summary files read only for safe scalar status fields. These are
# NOT exposed as artifact_available labels (kept off the allowlist) but feed
# drift_detected / bentoml_packaged / champion_challenger_decision.
MLOPS_LOOP_SUMMARY_RELPATH = "artifacts/mlops/mlops_loop_summary.json"
CHAMPION_CHALLENGER_RELPATH = "artifacts/mlops/champion_challenger/comparison.json"
BENTOML_BUILD_SUMMARY_RELPATH = "artifacts/mlops/bentoml/build_summary.json"


def default_artifact_specs(repo_root: Path | None = None) -> list[ArtifactSpec]:
    """Return the allowlisted artifact specs anchored at ``repo_root``."""

    root = repo_root or REPO_ROOT
    return [
        ArtifactSpec(key=key, path=root / relpath)
        for key, relpath in _ARTIFACT_RELPATHS.items()
    ]


def mlops_loop_summary_path(repo_root: Path | None = None) -> Path:
    root = repo_root or REPO_ROOT
    return root / MLOPS_LOOP_SUMMARY_RELPATH


def champion_challenger_path(repo_root: Path | None = None) -> Path:
    root = repo_root or REPO_ROOT
    return root / CHAMPION_CHALLENGER_RELPATH


def bentoml_build_summary_path(repo_root: Path | None = None) -> Path:
    root = repo_root or REPO_ROOT
    return root / BENTOML_BUILD_SUMMARY_RELPATH
