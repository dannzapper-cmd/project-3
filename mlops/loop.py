"""PR-05 MLOps loop orchestrator.

Runs, in order:

1. Evidently offline data drift + data quality reports on a temporal
   reference/current split (core; cannot be silently skipped).
2. MLflow model registry / metadata summary for the current model.
3. Champion/challenger comparison from existing PR-03/PR-04 artifacts.
4. Optional minimal BentoML packaging of the champion model.
5. A top-level aggregated summary.

The loop is idempotent: JSON artifacts are overwritten deterministically, and
registry/BentoML registration are deduplicated by source run id. It runs fully
locally/offline and never mutates PR-03/PR-04 metric files.
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from mlops import SCHEMA_VERSION
from mlops.comparison import (
    compare_models,
    extract_model_metrics,
    load_pr03_run,
    load_pr04_context,
)
from mlops.config import (
    DEFAULT_ML_CONFIG_PATH,
    DEFAULT_MLOPS_CONFIG_PATH,
    load_ml_config,
    load_mlops_config,
)
from mlops.drift import generate_reports
from mlops.packaging import package_champion
from mlops.registry import register_champion
from mlops.splitting import temporal_reference_current_split, split_periods

logger = logging.getLogger(__name__)

GLOBAL_LIMITATIONS = [
    "All inputs are synthetic (seed 42); nothing here reflects live InvenTree "
    "demand.",
    "Local file-store MLflow registry; no central server or production "
    "governance.",
    "Champion/challenger and cost figures are synthetic/simulated, not "
    "real-world claims.",
]


def _json_default(value: Any) -> Any:
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=_json_default),
        encoding="utf-8",
    )


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_featured_table(ml_config: dict[str, Any], data_cfg: dict[str, Any]):
    from ml.data import load_demand_training_table
    from ml.features import build_features, drop_rows_with_incomplete_features

    synthetic_dir = Path(data_cfg["synthetic_dir"])
    raw = load_demand_training_table(
        synthetic_dir,
        demand_file=data_cfg.get("demand_history_file", "demand_history.csv"),
        parts_file=data_cfg.get("parts_file", "parts.csv"),
    )
    featured = build_features(raw)
    return drop_rows_with_incomplete_features(featured)


def run_evidently_step(
    ml_config: dict[str, Any],
    mlops_config: dict[str, Any],
    artifact_root: Path,
) -> dict[str, Any]:
    data_cfg = mlops_config["data"]
    evidently_cfg = mlops_config["evidently"]
    featured = _load_featured_table(ml_config, data_cfg)

    reference_fraction = float(evidently_cfg.get("reference_fraction", 0.80))
    reference_df, current_df = temporal_reference_current_split(
        featured, reference_fraction=reference_fraction
    )
    periods = split_periods(reference_df, current_df)

    output_dir = artifact_root / "evidently"
    report = generate_reports(
        reference_df,
        current_df,
        output_dir,
        numerical_columns=evidently_cfg.get("numerical_columns"),
        categorical_columns=evidently_cfg.get("categorical_columns"),
    )
    report["reference_fraction"] = reference_fraction
    report["periods"] = periods
    return report


def run_registry_step(
    ml_config: dict[str, Any],
    mlops_config: dict[str, Any],
    artifact_root: Path,
) -> dict[str, Any]:
    mlflow_cfg = mlops_config["mlflow"]
    summary = register_champion(
        tracking_uri=mlflow_cfg.get("tracking_uri", "mlruns"),
        experiment_name=mlflow_cfg.get(
            "forecast_experiment", "demand_forecast_baseline"
        ),
        model_artifact=mlflow_cfg.get("forecast_model_artifact", "lightgbm_model"),
        registered_model_name=mlflow_cfg.get(
            "registered_model_name", "demand_forecast"
        ),
        champion_alias=mlflow_cfg.get("champion_alias", "champion"),
        champion_run_tag=mlflow_cfg.get(
            "champion_run_tag", "pr05_champion_run_id"
        ),
    )
    summary["schema_version"] = SCHEMA_VERSION
    summary["generated_at_utc"] = _now_utc()
    _write_json(
        artifact_root / "registry" / "registered_model_summary.json", summary
    )
    return summary


def _comparison_markdown(payload: dict[str, Any]) -> str:
    champ = payload["champion"]
    chal = payload["challenger"]
    comp = payload["comparison"]
    lines = [
        "# Champion / Challenger Comparison (PR-05)",
        "",
        f"- Generated (UTC): `{payload['generated_at_utc']}`",
        f"- Primary metric: **{payload['primary_metric']}** "
        f"({payload['primary_metric_direction']})",
        f"- Temporal split (PR-03): `{payload['temporal_split'].get('test_period')}`",
        "",
        "| Role | Model | Source | "
        f"{payload['primary_metric']} | rmse | mape |",
        "|------|-------|--------|------|------|------|",
        _model_row("champion", champ, payload["primary_metric"]),
        _model_row("challenger", chal, payload["primary_metric"]),
        "",
        f"- Absolute delta (challenger - champion): "
        f"`{comp.get('absolute_delta')}`",
        f"- Relative improvement (challenger vs champion): "
        f"`{comp.get('relative_improvement_pct')}`%",
        f"- Decision threshold: `{comp.get('decision_threshold_pct')}`%",
        "",
        f"## Decision: `{payload['decision']}`",
        "",
        payload["reason"],
        "",
        "### Warnings",
    ]
    for warning in payload.get("warnings", []):
        lines.append(f"- {warning}")
    lines.append("")
    lines.append("### Limitations")
    for limitation in payload.get("limitations", []):
        lines.append(f"- {limitation}")
    lines.append("")
    return "\n".join(lines)


def _model_row(role: str, model: dict[str, Any], primary: str) -> str:
    metrics = model.get("metrics", {})
    return (
        f"| {role} | {model.get('name')} | {model.get('source')} | "
        f"{metrics.get(primary)} | {metrics.get('rmse')} | {metrics.get('mape')} |"
    )


def run_comparison_step(
    ml_config: dict[str, Any],
    mlops_config: dict[str, Any],
    artifact_root: Path,
) -> dict[str, Any]:
    cc_cfg = mlops_config["champion_challenger"]
    mlflow_cfg = mlops_config["mlflow"]

    champion_model = cc_cfg.get("champion_model", "lightgbm")
    challenger_model = cc_cfg.get("challenger_model", "statsforecast")
    primary_metric = cc_cfg.get("primary_metric", "mae")
    direction = cc_cfg.get("primary_metric_direction", "lower_is_better")
    threshold = float(cc_cfg.get("decision_threshold_pct", 5.0))

    warnings_list: list[str] = []
    run = load_pr03_run(
        mlflow_cfg.get("tracking_uri", "mlruns"),
        mlflow_cfg.get("forecast_experiment", "demand_forecast_baseline"),
    )
    if run is None:
        champion_metrics: dict[str, Any] = {}
        challenger_metrics: dict[str, Any] = {}
        run_id = None
        warnings_list.append(
            "No PR-03 MLflow run found; champion/challenger metrics unavailable. "
            "Run `make train-ml` first."
        )
    else:
        run_id = run["run_id"]
        champion_metrics = extract_model_metrics(run["metrics"], champion_model)
        challenger_metrics = extract_model_metrics(run["metrics"], challenger_model)

    result = compare_models(
        champion_metrics,
        challenger_metrics,
        primary_metric=primary_metric,
        primary_metric_direction=direction,
        decision_threshold_pct=threshold,
    )

    pr04_path = Path(
        cc_cfg.get("pr04_summary_path", "artifacts/decision/decision_summary.json")
    )
    pr04_context = load_pr04_context(pr04_path)
    warnings_list.extend(pr04_context.get("warnings", []))
    warnings_list.extend(result.get("warnings", []))

    test_period = run["params"].get("test_start") if run else None
    if run and run["params"].get("test_start") and run["params"].get("test_end"):
        test_period = f"{run['params']['test_start']} to {run['params']['test_end']}"

    source = f"mlflow_run:{run_id}" if run_id else "unavailable"
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": _now_utc(),
        "primary_metric": primary_metric,
        "primary_metric_direction": direction,
        "temporal_split": {
            "source": "PR-03 demand_forecast_baseline run",
            "test_period": test_period,
            "train_fraction": ml_config.get("split", {}).get("train_fraction"),
        },
        "champion": {
            "name": champion_model,
            "role": "current/incumbent",
            "metrics": champion_metrics,
            "source": source,
        },
        "challenger": {
            "name": challenger_model,
            "role": "alternative baseline",
            "metrics": challenger_metrics,
            "source": source,
        },
        "comparison": result["comparison"],
        "decision": result["decision"],
        "reason": result["reason"],
        "supporting_context": {"pr04_cost_metrics": pr04_context},
        "warnings": sorted(set(warnings_list)),
        "limitations": list(GLOBAL_LIMITATIONS),
    }

    _write_json(artifact_root / "champion_challenger" / "comparison.json", payload)
    md_path = artifact_root / "champion_challenger" / "comparison.md"
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(_comparison_markdown(payload), encoding="utf-8")
    return payload


def run_bentoml_step(
    mlops_config: dict[str, Any],
    artifact_root: Path,
) -> dict[str, Any]:
    bento_cfg = mlops_config.get("bentoml", {})
    mlflow_cfg = mlops_config["mlflow"]
    output_path = artifact_root / "bentoml" / "build_summary.json"

    if not bento_cfg.get("enabled", True):
        summary = {
            "status": "disabled",
            "reason": "BentoML packaging disabled in mlops/config.yaml",
        }
    else:
        summary = package_champion(
            tracking_uri=mlflow_cfg.get("tracking_uri", "mlruns"),
            experiment_name=mlflow_cfg.get(
                "forecast_experiment", "demand_forecast_baseline"
            ),
            model_artifact=mlflow_cfg.get(
                "forecast_model_artifact", "lightgbm_model"
            ),
            model_name=bento_cfg.get("model_name", "invforge_demand_forecast"),
        )
    summary["schema_version"] = SCHEMA_VERSION
    summary["generated_at_utc"] = _now_utc()
    _write_json(output_path, summary)
    return summary


def run_loop(
    *,
    mlops_config_path: Path = DEFAULT_MLOPS_CONFIG_PATH,
    ml_config_path: Path = DEFAULT_ML_CONFIG_PATH,
) -> dict[str, Any]:
    """Execute the full MLOps loop and return an aggregated summary."""

    mlops_config = load_mlops_config(mlops_config_path)
    ml_config = load_ml_config(ml_config_path)
    artifacts_cfg = mlops_config.get("artifacts", {})
    artifact_root = Path(artifacts_cfg.get("root", "artifacts/mlops"))
    artifact_root.mkdir(parents=True, exist_ok=True)

    logger.info("Running Evidently drift / data quality reports...")
    evidently_summary = run_evidently_step(ml_config, mlops_config, artifact_root)

    logger.info("Running MLflow registry / metadata step...")
    registry_summary = run_registry_step(ml_config, mlops_config, artifact_root)

    logger.info("Running champion/challenger comparison...")
    comparison_summary = run_comparison_step(ml_config, mlops_config, artifact_root)

    logger.info("Running BentoML packaging step...")
    bentoml_summary = run_bentoml_step(mlops_config, artifact_root)

    aggregate = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": _now_utc(),
        "scope": "PR-05 local MLOps loop",
        "data_source": "synthetic",
        "seed": 42,
        "steps": {
            "evidently": {
                "status": evidently_summary.get("status"),
                "dataset_drift_detected": evidently_summary.get(
                    "drift_summary", {}
                ).get("dataset_drift_detected"),
                "drifted_share": evidently_summary.get("drift_summary", {}).get(
                    "drifted_share"
                ),
                "periods": evidently_summary.get("periods"),
            },
            "registry": {
                "registry_strategy": registry_summary.get("registry_strategy"),
                "registered": registry_summary.get("champion", {}).get(
                    "registered"
                ),
                "version": registry_summary.get("champion", {}).get("version"),
            },
            "champion_challenger": {
                "decision": comparison_summary.get("decision"),
                "primary_metric": comparison_summary.get("primary_metric"),
            },
            "bentoml": {
                "status": bentoml_summary.get("status"),
                "deferred_to": bentoml_summary.get("deferred_to"),
            },
        },
        "artifacts": {
            "evidently_dir": str(artifact_root / "evidently"),
            "registry_summary": str(
                artifact_root / "registry" / "registered_model_summary.json"
            ),
            "comparison_json": str(
                artifact_root / "champion_challenger" / "comparison.json"
            ),
            "comparison_md": str(
                artifact_root / "champion_challenger" / "comparison.md"
            ),
            "bentoml_build_summary": str(
                artifact_root / "bentoml" / "build_summary.json"
            ),
        },
        "warnings": [
            "Synthetic data only.",
            "Local registry; ephemeral mlruns/ store.",
            "Not a production deployment or real-world performance claim.",
        ],
        "limitations": list(GLOBAL_LIMITATIONS),
    }
    _write_json(artifact_root / "mlops_loop_summary.json", aggregate)
    return aggregate


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the PR-05 MLOps loop.")
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_MLOPS_CONFIG_PATH,
        help="Path to the MLOps loop YAML configuration",
    )
    parser.add_argument(
        "--ml-config",
        type=Path,
        default=DEFAULT_ML_CONFIG_PATH,
        help="Path to the PR-03/PR-04 YAML configuration (read-only)",
    )
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = parse_args()
    aggregate = run_loop(
        mlops_config_path=args.config,
        ml_config_path=args.ml_config,
    )
    steps = aggregate["steps"]
    print("MLOps loop complete.")
    print(f"  Evidently drift detected: {steps['evidently']['dataset_drift_detected']}")
    print(f"  Registry strategy:        {steps['registry']['registry_strategy']}")
    print(f"  Champion/challenger:      {steps['champion_challenger']['decision']}")
    print(f"  BentoML packaging:        {steps['bentoml']['status']}")
    print(f"  Summary:                  {aggregate['artifacts']['evidently_dir']}/..")


if __name__ == "__main__":
    main()
