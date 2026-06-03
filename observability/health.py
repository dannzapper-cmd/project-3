"""Health/status builder for the PR-07 AI Operations observability layer.

Returns the exact B3 health shape. Reads only existence/mtime and a small set
of allowlisted safe scalar summary fields (drift status, champion/challenger
decision, BentoML packaging status) from PR-04/PR-05 artifacts. Never returns
file paths, raw payloads, secrets, or PII. Never raises: any read/parse error
degrades gracefully to a safe default.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from observability.artifacts import (
    ArtifactSpec,
    bentoml_build_summary_path,
    champion_challenger_path,
    default_artifact_specs,
    mlops_loop_summary_path,
)
from observability.logging import get_logger

PR_STAGE = "PR-07"

# Allowed champion/challenger decision vocabulary (PR-05 native values plus
# the safe fallbacks). Never a raw model name, path, or numeric score.
ALLOWED_DECISIONS: tuple[str, ...] = (
    "promote_challenger",
    "keep_champion",
    "manual_review",
    "no_comparison",
    "unknown",
)

_logger = get_logger("health")


def _read_json(path: Path) -> dict[str, Any] | None:
    """Read a small JSON object safely. Returns ``None`` on any error."""

    try:
        if not path.is_file():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _drift_detected(mlops_loop_path: Path) -> bool | None:
    """Return drift status from the MLOps loop summary, or ``None`` if unknown.

    Reads only the single boolean ``steps.evidently.dataset_drift_detected``
    field (PATCH 8: no deep Evidently parsing in PR-07).
    """

    payload = _read_json(mlops_loop_path)
    if payload is None:
        return None
    evidently = payload.get("steps", {}).get("evidently", {})
    value = evidently.get("dataset_drift_detected")
    if isinstance(value, bool):
        return value
    return None


def _champion_challenger_decision(comparison_path: Path) -> str:
    """Return a safe champion/challenger decision label.

    ``no_comparison`` when the artifact is absent; ``unknown`` when present but
    the decision value is not in the allowed vocabulary.
    """

    payload = _read_json(comparison_path)
    if payload is None:
        return "no_comparison"
    decision = payload.get("decision")
    if decision in ALLOWED_DECISIONS and decision not in {"no_comparison", "unknown"}:
        return str(decision)
    return "unknown"


def _bentoml_packaged(bentoml_path: Path) -> bool | None:
    """Return True if the champion model was packaged, False/None otherwise."""

    payload = _read_json(bentoml_path)
    if payload is None:
        return None
    return payload.get("status") == "packaged"


def build_health_status(
    specs: list[ArtifactSpec] | None = None,
    *,
    repo_root: Path | None = None,
    mlops_loop_path: Path | None = None,
    comparison_path: Path | None = None,
    bentoml_path: Path | None = None,
) -> dict[str, Any]:
    """Build the B3 health payload. Never raises.

    With nonexistent artifact paths this returns status ``unavailable`` (or
    ``degraded`` if some artifacts exist). With all artifacts present it
    returns ``ok``.
    """

    artifact_specs = specs if specs is not None else default_artifact_specs(repo_root)
    loop_path = mlops_loop_path or mlops_loop_summary_path(repo_root)
    cc_path = comparison_path or champion_challenger_path(repo_root)
    bento_path = bentoml_path or bentoml_build_summary_path(repo_root)

    artifacts: dict[str, str] = {}
    present = 0
    for spec in artifact_specs:
        try:
            exists = spec.path.is_file()
        except OSError:
            exists = False
        artifacts[spec.key] = "ok" if exists else "missing"
        if exists:
            present += 1

    total = len(artifact_specs)
    if present == 0:
        status = "unavailable"
    elif present == total:
        status = "ok"
    else:
        status = "degraded"

    payload = {
        "status": status,
        "pr_stage": PR_STAGE,
        "artifacts": artifacts,
        "drift_detected": _drift_detected(loop_path),
        "bentoml_packaged": _bentoml_packaged(bento_path),
        "champion_challenger_decision": _champion_challenger_decision(cc_path),
    }

    _logger.log(
        "health_status_built",
        level="info" if status != "unavailable" else "warning",
        status=status,
    )
    return payload
