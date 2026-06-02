"""Offline Evidently data drift and data quality reports (Evidently 0.7.x).

This module uses only the Evidently API confirmed available in the pinned
version (``evidently>=0.7.0,<0.8.0``):

* ``from evidently import Report, Dataset, DataDefinition``
* ``from evidently.presets import DataDriftPreset, DataSummaryPreset``
* ``Report([...]).run(current_data, reference_data)`` -> Snapshot
* ``snapshot.save_html(...)`` / ``snapshot.save_json(...)`` / ``snapshot.dict()``

Reports are deterministic given the same input data and always overwrite the
previous artifacts (idempotent). Evidently is imported lazily so that the rest
of the MLOps loop and its tests can run without the ``mlops`` dependency group.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from mlops.splitting import split_periods, temporal_reference_current_split

WARNINGS = [
    "Drift is computed on synthetic data; results do not reflect live demand.",
    "Reports are offline diagnostics, not a monitoring service or alerting "
    "system.",
]


class DriftFeatureError(ValueError):
    """Raised when configured drift feature columns are missing from the data."""


def _resolve_columns(
    df: pd.DataFrame,
    numerical_columns: list[str] | None,
    categorical_columns: list[str] | None,
) -> tuple[list[str], list[str]]:
    """Validate that requested columns exist; fail clearly if any are missing."""

    numerical = list(numerical_columns or [])
    categorical = list(categorical_columns or [])
    requested = numerical + categorical
    if not requested:
        raise DriftFeatureError(
            "No drift columns configured. Provide numerical_columns and/or "
            "categorical_columns."
        )

    missing = [col for col in requested if col not in df.columns]
    if missing:
        raise DriftFeatureError(
            "Configured drift feature columns are missing from the data: "
            f"{sorted(missing)}. Available columns: {sorted(df.columns)}"
        )
    return numerical, categorical


def _build_datasets(
    reference_df: pd.DataFrame,
    current_df: pd.DataFrame,
    numerical: list[str],
    categorical: list[str],
) -> tuple[Any, Any]:
    from evidently import DataDefinition, Dataset

    columns = numerical + categorical
    data_definition = DataDefinition(
        numerical_columns=numerical or None,
        categorical_columns=categorical or None,
    )
    reference_dataset = Dataset.from_pandas(
        reference_df[columns].reset_index(drop=True),
        data_definition=data_definition,
    )
    current_dataset = Dataset.from_pandas(
        current_df[columns].reset_index(drop=True),
        data_definition=data_definition,
    )
    return reference_dataset, current_dataset


def summarize_drift(snapshot_dict: dict[str, Any]) -> dict[str, Any]:
    """Extract a small, stable drift summary from an Evidently snapshot dict.

    Stable schema (PR-06 consumable)::

        {
          "dataset_drift_detected": bool,
          "drifted_columns_count": int,
          "drifted_share": float,
          "drift_share_threshold": float,
          "columns": [
            {"column": str, "method": str, "threshold": float,
             "score": float, "drifted": bool}, ...
          ]
        }
    """

    metrics = snapshot_dict.get("metrics", [])
    drifted_count = 0
    drifted_share = 0.0
    drift_share_threshold = 0.0
    columns: list[dict[str, Any]] = []

    for metric in metrics:
        config = metric.get("config", {})
        metric_type = config.get("type", "")
        value = metric.get("value")
        if metric_type.endswith("DriftedColumnsCount"):
            drift_share_threshold = float(config.get("drift_share", 0.0))
            if isinstance(value, dict):
                drifted_count = int(value.get("count", 0))
                drifted_share = float(value.get("share", 0.0))
        elif metric_type.endswith("ValueDrift"):
            column = config.get("column")
            threshold = float(config.get("threshold", 0.05))
            score = float(value) if value is not None else float("nan")
            # p-value based tests: drift when the score is below the threshold.
            drifted = bool(score < threshold)
            columns.append(
                {
                    "column": column,
                    "method": config.get("method"),
                    "threshold": threshold,
                    "score": score,
                    "drifted": drifted,
                }
            )

    dataset_drift_detected = bool(
        drift_share_threshold > 0 and drifted_share >= drift_share_threshold
    )
    columns.sort(key=lambda item: str(item["column"]))
    return {
        "dataset_drift_detected": dataset_drift_detected,
        "drifted_columns_count": drifted_count,
        "drifted_share": drifted_share,
        "drift_share_threshold": drift_share_threshold,
        "columns": columns,
    }


def generate_reports(
    reference_df: pd.DataFrame,
    current_df: pd.DataFrame,
    output_dir: Path,
    *,
    numerical_columns: list[str] | None = None,
    categorical_columns: list[str] | None = None,
) -> dict[str, Any]:
    """Generate data drift and data quality reports; return a stable summary.

    Always overwrites existing report artifacts. Raises
    :class:`DriftFeatureError` if configured columns are missing.
    """

    from evidently import Report
    from evidently.presets import DataDriftPreset, DataSummaryPreset

    numerical, categorical = _resolve_columns(
        current_df, numerical_columns, categorical_columns
    )
    _resolve_columns(reference_df, numerical, categorical)

    output_dir.mkdir(parents=True, exist_ok=True)
    reference_dataset, current_dataset = _build_datasets(
        reference_df, current_df, numerical, categorical
    )

    drift_report = Report([DataDriftPreset()])
    drift_snapshot = drift_report.run(current_dataset, reference_dataset)
    drift_html = output_dir / "data_drift_report.html"
    drift_json = output_dir / "data_drift_report.json"
    drift_snapshot.save_html(str(drift_html))
    drift_snapshot.save_json(str(drift_json))

    quality_report = Report([DataSummaryPreset()])
    quality_snapshot = quality_report.run(current_dataset, reference_dataset)
    quality_html = output_dir / "data_quality_report.html"
    quality_json = output_dir / "data_quality_report.json"
    quality_snapshot.save_html(str(quality_html))
    quality_snapshot.save_json(str(quality_json))

    drift_summary = summarize_drift(drift_snapshot.dict())

    return {
        "status": "generated",
        "evidently_version": _evidently_version(),
        "numerical_columns": numerical,
        "categorical_columns": categorical,
        "drift_summary": drift_summary,
        "artifacts": {
            "data_drift_report_html": str(drift_html),
            "data_drift_report_json": str(drift_json),
            "data_quality_report_html": str(quality_html),
            "data_quality_report_json": str(quality_json),
        },
        "warnings": list(WARNINGS),
    }


def _evidently_version() -> str:
    try:
        import evidently

        return str(getattr(evidently, "__version__", "unknown"))
    except Exception:  # pragma: no cover - defensive
        return "unknown"


def build_reference_current(
    featured_df: pd.DataFrame,
    *,
    reference_fraction: float,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, str]]:
    """Split an engineered feature frame and return periods metadata."""

    reference_df, current_df = temporal_reference_current_split(
        featured_df, reference_fraction=reference_fraction
    )
    periods = split_periods(reference_df, current_df)
    return reference_df, current_df, periods
