"""Evidently drift report smoke + schema tests.

Skips automatically when the optional ``mlops`` dependency group (Evidently) is
not installed, so the core test run stays lightweight. The drift summary parser
is exercised without Evidently using a captured snapshot-dict shape.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from mlops.drift import DriftFeatureError, summarize_drift


def test_summarize_drift_schema_without_evidently():
    snapshot_dict = {
        "metrics": [
            {
                "config": {
                    "type": "evidently:metric_v2:DriftedColumnsCount",
                    "drift_share": 0.5,
                },
                "value": {"count": 1.0, "share": 0.5},
            },
            {
                "config": {
                    "type": "evidently:metric_v2:ValueDrift",
                    "column": "a",
                    "method": "K-S p_value",
                    "threshold": 0.05,
                },
                "value": 1e-20,
            },
            {
                "config": {
                    "type": "evidently:metric_v2:ValueDrift",
                    "column": "b",
                    "method": "chi-square p_value",
                    "threshold": 0.05,
                },
                "value": 0.55,
            },
        ]
    }
    summary = summarize_drift(snapshot_dict)
    assert summary["dataset_drift_detected"] is True
    assert summary["drifted_columns_count"] == 1
    assert summary["drift_share_threshold"] == 0.5
    columns = {c["column"]: c for c in summary["columns"]}
    assert columns["a"]["drifted"] is True
    assert columns["b"]["drifted"] is False


def test_generate_reports_smoke(tmp_path):
    pytest.importorskip("evidently")
    from mlops.drift import generate_reports

    rng = np.random.default_rng(42)
    reference = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=300, freq="D"),
            "quantity_demand": rng.normal(10, 2, 300),
            "category_id": rng.integers(0, 3, 300).astype(str),
        }
    )
    current = pd.DataFrame(
        {
            "date": pd.date_range("2024-11-01", periods=120, freq="D"),
            "quantity_demand": rng.normal(13, 2, 120),
            "category_id": rng.integers(0, 3, 120).astype(str),
        }
    )

    report = generate_reports(
        reference,
        current,
        tmp_path,
        numerical_columns=["quantity_demand"],
        categorical_columns=["category_id"],
    )
    assert report["status"] == "generated"
    for key in (
        "data_drift_report_html",
        "data_drift_report_json",
        "data_quality_report_html",
        "data_quality_report_json",
    ):
        assert (tmp_path / key.replace("_html", ".html").replace("_json", ".json")
                ).name in report["artifacts"][key]
    assert (tmp_path / "data_drift_report.json").exists()
    assert (tmp_path / "data_drift_report.html").exists()
    assert (tmp_path / "data_quality_report.json").exists()
    # The drift summary is a stable schema.
    summary = report["drift_summary"]
    assert set(summary) >= {
        "dataset_drift_detected",
        "drifted_columns_count",
        "drifted_share",
        "drift_share_threshold",
        "columns",
    }
    # Native JSON is valid.
    json.loads((tmp_path / "data_drift_report.json").read_text(encoding="utf-8"))


def test_missing_columns_fail_clearly(tmp_path):
    pytest.importorskip("evidently")
    from mlops.drift import generate_reports

    reference = pd.DataFrame({"a": [1, 2, 3]})
    current = pd.DataFrame({"a": [1, 2, 3]})
    with pytest.raises(DriftFeatureError):
        generate_reports(
            reference,
            current,
            tmp_path,
            numerical_columns=["does_not_exist"],
            categorical_columns=[],
        )
