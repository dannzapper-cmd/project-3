"""Tests for minimal BentoML packaging behaviour.

Skips automatically when the optional ``mlops`` dependency group (BentoML) is
not installed. The deferral summary builder is checked without BentoML.
"""

from __future__ import annotations

import pytest

from mlops.packaging import DEFERRED_TO, _deferred, package_champion


def test_deferred_summary_schema():
    summary = _deferred("example conflict")
    assert summary["status"] == "deferred"
    assert summary["reason"] == "example conflict"
    assert summary["deferred_to"] == DEFERRED_TO
    assert summary["deferred_to"] == "PR-10 or PR-11"
    assert "warning" in summary


def test_package_skips_when_no_experiment(tmp_path, monkeypatch):
    pytest.importorskip("bentoml")
    monkeypatch.setenv("MLFLOW_ALLOW_FILE_STORE", "true")
    monkeypatch.setenv("BENTOML_DO_NOT_TRACK", "true")

    summary = package_champion(
        tracking_uri=f"file:{tmp_path / 'empty_mlruns'}",
        experiment_name="does_not_exist",
        model_artifact="lightgbm_model",
        model_name="invforge_demand_forecast_test",
    )
    assert summary["status"] == "skipped"
    assert "warnings" in summary
