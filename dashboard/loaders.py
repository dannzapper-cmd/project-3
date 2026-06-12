"""Read-only artifact loaders for the PR-06 AI Operations Dashboard.

Every loader returns ``{"status": "ok", "data": ..., "path": ..., "mtime": ...}``
or ``{"status": "missing", "reason": ..., "commands": [...]}``. Loaders never
trigger pipelines, subprocesses, or metric recomputation.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from dashboard.paths import (
    BENTOML_BUILD_SUMMARY,
    CHAMPION_CHALLENGER,
    CMD_DECISION_INTEL,
    CMD_GENERATE_DATA,
    CMD_MLOPS_LOOP,
    CMD_TRAIN_ML,
    DECISION_RECOMMENDATIONS,
    DECISION_SUMMARY,
    DEFAULT_DECISION_DIR,
    DEFAULT_MLOPS_DIR,
    DEFAULT_PROCESSED_DIR,
    DEFAULT_SYNTHETIC_DIR,
    EVIDENTLY_DRIFT_JSON,
    EVIDENTLY_QUALITY_JSON,
    MLRUNS_DIR,
    MLOPS_LOOP_SUMMARY,
    REGISTRY_SUMMARY,
    RETRAINING_DIR,
    SYNTHETIC_MARKERS,
)
from dashboard.types import LoaderMissing, LoaderOk, LoaderResult


def format_mtime(path: Path) -> str:
    """Return filesystem mtime as ``YYYY-MM-DD HH:MM`` or ``Unknown``."""

    try:
        ts = path.stat().st_mtime
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
    except OSError:
        return "Unknown"


def _missing(reason: str, commands: list[str]) -> LoaderMissing:
    return {"status": "missing", "reason": reason, "commands": commands}


def _ok(path: Path, data: Any) -> LoaderOk:
    return {
        "status": "ok",
        "data": data,
        "path": str(path),
        "mtime": format_mtime(path),
    }


def _load_json_file(
    path: Path,
    *,
    label: str,
    commands: list[str],
    empty_message: str | None = None,
) -> LoaderResult:
    if not path.is_file():
        return _missing(
            f"{label} not found at {path}.",
            commands,
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return _missing(
            f"{label} at {path} could not be parsed: {exc}",
            commands,
        )
    if empty_message and not payload:
        return _missing(empty_message, commands)
    return _ok(path, payload)


def load_synthetic_data_status(
    synthetic_dir: Path | None = None,
) -> LoaderResult:
    # Schema: {"files_present": list[str], "files_missing": list[str],
    #          "ready": bool} | source: data/synthetic/output/*.csv
    # Missing fields: [] | Optional fields: []
    root = synthetic_dir or DEFAULT_SYNTHETIC_DIR
    if not root.is_dir():
        return _missing(
            f"Synthetic data directory not found at {root}.",
            [CMD_GENERATE_DATA],
        )

    present: list[str] = []
    missing: list[str] = []
    for name in SYNTHETIC_MARKERS:
        if (root / name).is_file():
            present.append(name)
        else:
            missing.append(name)

    if not present:
        return _missing(
            f"No synthetic CSV markers found under {root}.",
            [CMD_GENERATE_DATA],
        )

    data = {
        "synthetic_dir": str(root),
        "files_present": present,
        "files_missing": missing,
        "ready": len(missing) == 0,
    }
    marker_path = root / present[0]
    return _ok(marker_path, data)


def load_decision_summary(
    path: Path | None = None,
) -> LoaderResult:
    # Schema: {"scope": str, "data_source": str, "test_period": str,
    #          "recommendation_rows": int, "cost_metrics": dict,
    #          "policy_optimization": dict, "interval_metrics": dict,
    #          "warnings": list, "limitations": list, ...}
    # | source: artifacts/decision/decision_summary.json
    # Missing fields: [] | Optional fields: ["run_id", "artifacts"]
    target = path or DECISION_SUMMARY
    result = _load_json_file(
        target,
        label="Decision summary",
        commands=[CMD_GENERATE_DATA, CMD_DECISION_INTEL],
        empty_message="Decision summary JSON is empty.",
    )
    if result["status"] == "missing":
        return result

    data = result["data"]
    if not isinstance(data, dict):
        return _missing("Decision summary is not a JSON object.", [CMD_DECISION_INTEL])

    rows = data.get("recommendation_rows")
    if rows is not None and int(rows) <= 0:
        return _missing(
            "Decision summary has zero recommendation rows.",
            [CMD_DECISION_INTEL],
        )
    return result


def load_decision_recommendations(
    path: Path | None = None,
) -> LoaderResult:
    # Schema: pandas DataFrame columns per PR-04 (part_id, safety_stock,
    # reorder_point, eoq, stockout_risk, risk_level, prediction, ...)
    # | source: artifacts/decision/decision_recommendations.csv
    # Missing fields: [] | Optional fields: []
    target = path or DECISION_RECOMMENDATIONS
    if not target.is_file():
        return _missing(
            f"Decision recommendations CSV not found at {target}.",
            [CMD_GENERATE_DATA, CMD_DECISION_INTEL],
        )
    try:
        frame = pd.read_csv(target)
    except (OSError, pd.errors.EmptyDataError, ValueError) as exc:
        return _missing(
            f"Decision recommendations at {target} could not be read: {exc}",
            [CMD_DECISION_INTEL],
        )

    if frame.empty:
        return _missing(
            "Decision recommendations CSV has no rows.",
            [CMD_DECISION_INTEL],
        )

    required = {
        "part_id",
        "safety_stock",
        "reorder_point",
        "eoq",
        "stockout_risk",
        "risk_level",
    }
    missing_cols = required - set(frame.columns)
    if missing_cols:
        return _missing(
            f"Decision recommendations missing columns: {sorted(missing_cols)}.",
            [CMD_DECISION_INTEL],
        )

    return _ok(target, frame)


def load_champion_challenger_comparison(
    path: Path | None = None,
) -> LoaderResult:
    # Schema: {"schema_version": str, "primary_metric": str,
    #          "champion": {"name": str, "metrics": {"mae", "rmse", "mape"}},
    #          "challenger": {"name": str, "metrics": dict},
    #          "comparison": dict, "decision": str, "reason": str}
    # | source: artifacts/mlops/champion_challenger/comparison.json
    # Missing fields: [] | Optional fields: ["supporting_context"]
    target = path or CHAMPION_CHALLENGER
    result = _load_json_file(
        target,
        label="Champion/challenger comparison",
        commands=[CMD_GENERATE_DATA, CMD_TRAIN_ML, CMD_MLOPS_LOOP],
    )
    if result["status"] == "missing":
        return result

    data = result["data"]
    champ_metrics = (data.get("champion") or {}).get("metrics") or {}
    chal_metrics = (data.get("challenger") or {}).get("metrics") or {}
    primary = data.get("primary_metric", "mae")
    has_champ = champ_metrics.get(primary) is not None
    has_chal = chal_metrics.get(primary) is not None
    if not has_champ and not has_chal:
        return _missing(
            "Champion/challenger comparison has no usable primary metric values. "
            "Run training and the MLOps loop first.",
            [CMD_TRAIN_ML, CMD_MLOPS_LOOP],
        )
    return result


def load_mlops_loop_summary(
    path: Path | None = None,
) -> LoaderResult:
    # Schema: {"schema_version": str, "steps": {"evidently", "registry",
    #          "champion_challenger", "bentoml"}, "artifacts": dict, "warnings": list}
    # | source: artifacts/mlops/mlops_loop_summary.json
    # Missing fields: [] | Optional fields: []
    target = path or MLOPS_LOOP_SUMMARY
    return _load_json_file(
        target,
        label="MLOps loop summary",
        commands=[CMD_GENERATE_DATA, CMD_TRAIN_ML, CMD_MLOPS_LOOP],
        empty_message="MLOps loop summary JSON is empty.",
    )


def load_registry_summary(
    path: Path | None = None,
) -> LoaderResult:
    # Schema: {"registry_strategy": str, "model_name": str,
    #          "champion": {"registered": bool, "version": str}, "warnings": list}
    # | source: artifacts/mlops/registry/registered_model_summary.json
    # Missing fields: [] | Optional fields: ["champion.metrics", "champion.params"]
    target = path or REGISTRY_SUMMARY
    return _load_json_file(
        target,
        label="MLflow registry summary",
        commands=[CMD_GENERATE_DATA, CMD_TRAIN_ML, CMD_MLOPS_LOOP],
    )


def load_bentoml_build_summary(
    path: Path | None = None,
) -> LoaderResult:
    # Schema: {"status": str, "reason": str, "deferred_to": str, "warnings": list}
    # | source: artifacts/mlops/bentoml/build_summary.json
    # Missing fields: [] | Optional fields: ["bentoml_model_tag", "mlflow_run_id"]
    target = path or BENTOML_BUILD_SUMMARY
    return _load_json_file(
        target,
        label="BentoML build summary",
        commands=[CMD_GENERATE_DATA, CMD_TRAIN_ML, CMD_MLOPS_LOOP],
    )


def load_evidently_artifact_status(
    drift_path: Path | None = None,
    quality_path: Path | None = None,
) -> LoaderResult:
    # Schema: {"drift_report": bool, "quality_report": bool,
    #          "dataset_drift_detected": bool|None}
    # | source: artifacts/mlops/evidently/*.json (existence + optional drift parse)
    # Missing fields: [] | Optional fields: ["dataset_drift_detected"]
    drift = drift_path or EVIDENTLY_DRIFT_JSON
    quality = quality_path or EVIDENTLY_QUALITY_JSON
    if not drift.is_file() and not quality.is_file():
        return _missing(
            "Evidently drift/quality reports not found.",
            [CMD_GENERATE_DATA, CMD_MLOPS_LOOP],
        )

    drift_detected: bool | None = None
    anchor = drift if drift.is_file() else quality
    if drift.is_file():
        try:
            drift_payload = json.loads(drift.read_text(encoding="utf-8"))
            metrics = drift_payload.get("metrics", [])
            for metric in metrics:
                config = metric.get("config", {})
                if str(config.get("type", "")).endswith("DriftedColumnsCount"):
                    value = metric.get("value") or {}
                    share = float(value.get("share", 0.0))
                    threshold = float(config.get("drift_share", 0.5))
                    drift_detected = bool(threshold > 0 and share >= threshold)
                    break
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            drift_detected = None

    data = {
        "drift_report": drift.is_file(),
        "quality_report": quality.is_file(),
        "dataset_drift_detected": drift_detected,
        "drift_path": str(drift),
        "quality_path": str(quality),
    }
    return _ok(anchor, data)


def derive_overview_status(
    *,
    synthetic: LoaderResult,
    comparison: LoaderResult,
    decision_summary: LoaderResult,
    mlops_summary: LoaderResult,
) -> dict[str, str]:
    """Map loader results to high-level section status labels."""

    def _label(result: LoaderResult) -> str:
        return "ok" if result["status"] == "ok" else "missing"

    return {
        "data": _label(synthetic),
        "ml_forecast": _label(comparison),
        "decision": _label(decision_summary),
        "mlops": _label(mlops_summary),
    }


def _path_ready(path: Path) -> bool:
    if path.is_file():
        return True
    if path.is_dir():
        try:
            return any(path.iterdir())
        except OSError:
            return False
    return False


def derive_system_flow_steps(
    *,
    synthetic: LoaderResult,
    comparison: LoaderResult,
    decision_summary: LoaderResult,
    mlops_summary: LoaderResult,
) -> list[dict[str, str]]:
    """Build read-only pipeline step cards for the System Flow dashboard section."""

    def _status(result: LoaderResult, path: Path) -> str:
        if result["status"] == "ok":
            return "ok"
        if _path_ready(path):
            return "ok"
        return "missing"

    pipeline: list[dict[str, str]] = [
        {
            "kind": "pipeline",
            "step": "1",
            "title": "Data source",
            "command": CMD_GENERATE_DATA,
            "detail": "Synthetic CSVs (seed 42) by default; optional InvenTree ingest.",
            "artifact_path": str(DEFAULT_SYNTHETIC_DIR),
            "status": _status(synthetic, DEFAULT_SYNTHETIC_DIR),
        },
        {
            "kind": "pipeline",
            "step": "2",
            "title": "Data validation",
            "command": 'make UV="uv" validate-data',
            "detail": "Pandera schemas on synthetic/processed CSVs.",
            "artifact_path": str(DEFAULT_PROCESSED_DIR),
            "status": "ok" if _path_ready(DEFAULT_SYNTHETIC_DIR) else "missing",
        },
        {
            "kind": "pipeline",
            "step": "3",
            "title": "Forecasting models",
            "command": CMD_TRAIN_ML,
            "detail": "LightGBM + StatsForecast + Croston/SBA; logs to MLflow.",
            "artifact_path": str(MLRUNS_DIR),
            "status": _status(comparison, MLRUNS_DIR),
        },
        {
            "kind": "pipeline",
            "step": "4",
            "title": "Decision intelligence",
            "command": CMD_DECISION_INTEL,
            "detail": "Safety stock, ROP, EOQ, stockout risk from forecast quantiles.",
            "artifact_path": str(DEFAULT_DECISION_DIR),
            "status": _status(decision_summary, DEFAULT_DECISION_DIR),
        },
        {
            "kind": "pipeline",
            "step": "5",
            "title": "MLOps loop",
            "command": CMD_MLOPS_LOOP,
            "detail": "Evidently drift, MLflow registry, champion/challenger, BentoML.",
            "artifact_path": str(DEFAULT_MLOPS_DIR),
            "status": _status(mlops_summary, DEFAULT_MLOPS_DIR),
        },
    ]

    retraining_status = "ok" if _path_ready(RETRAINING_DIR) else "optional"
    companions: list[dict[str, str]] = [
        {
            "kind": "companion",
            "step": "6",
            "title": "API health / metrics",
            "command": 'make UV="uv" observability-api',
            "detail": "FastAPI `/health` and `/metrics` summarize artifact presence.",
            "artifact_path": "http://localhost:8001/health",
            "status": "companion",
        },
        {
            "kind": "companion",
            "step": "7",
            "title": "Observability",
            "command": 'make UV="uv" observability-up',
            "detail": "Local Prometheus + Grafana (Docker) or kind LGTM profile.",
            "artifact_path": "observability/ · deploy/k8s/observability/",
            "status": "companion",
        },
        {
            "kind": "companion",
            "step": "8",
            "title": "Lineage",
            "command": "make lineage-up && make lineage-smoke",
            "detail": "OpenLineage → Marquez for retraining job `invforge.retraining`.",
            "artifact_path": str(RETRAINING_DIR),
            "status": retraining_status,
        },
    ]
    return pipeline + companions
