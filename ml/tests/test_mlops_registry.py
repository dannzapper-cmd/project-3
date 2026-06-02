"""Tests for MLflow registry metadata/tagging and fallback behaviour."""

from __future__ import annotations

import numpy as np
import pytest

from mlops.registry import (
    STRATEGY_FALLBACK,
    STRATEGY_NATIVE,
    register_champion,
)

EXPERIMENT = "demand_forecast_baseline"
MODEL_NAME = "demand_forecast"


@pytest.fixture
def populated_tracking_uri(tmp_path, monkeypatch):
    """Create a local file-store run with a logged sklearn model + metrics."""

    monkeypatch.setenv("MLFLOW_ALLOW_FILE_STORE", "true")
    import mlflow
    from sklearn.dummy import DummyRegressor

    uri = f"file:{tmp_path / 'mlruns'}"
    mlflow.set_tracking_uri(uri)
    mlflow.set_experiment(EXPERIMENT)

    model = DummyRegressor().fit(np.array([[1.0], [2.0]]), [1.0, 2.0])
    with mlflow.start_run():
        mlflow.log_metric("lightgbm_mae", 2.113)
        mlflow.log_metric("statsforecast_mae", 2.088)
        mlflow.sklearn.log_model(model, name="lightgbm_model")
    return uri


def _register(uri):
    return register_champion(
        tracking_uri=uri,
        experiment_name=EXPERIMENT,
        model_artifact="lightgbm_model",
        registered_model_name=MODEL_NAME,
        champion_alias="champion",
        champion_run_tag="pr05_champion_run_id",
    )


def test_native_registration_with_alias_and_tags(populated_tracking_uri):
    summary = _register(populated_tracking_uri)
    assert summary["registry_strategy"] == STRATEGY_NATIVE
    champ = summary["champion"]
    assert champ["registered"] is True
    assert champ["alias"] == "champion"
    assert champ["tags"]["scope"] == "pr05"
    assert champ["tags"]["data_source"] == "synthetic"
    assert champ["tags"]["pr05_champion_run_id"] == champ["run_id"]
    assert "metrics" in champ and "params" in champ
    assert "limitations" in summary and summary["limitations"]


def test_registration_is_idempotent(populated_tracking_uri):
    first = _register(populated_tracking_uri)
    second = _register(populated_tracking_uri)
    assert first["champion"]["version"] == second["champion"]["version"]
    assert second["idempotency"]["action"] == "skipped_existing"


def test_fallback_when_experiment_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("MLFLOW_ALLOW_FILE_STORE", "true")
    import mlflow

    uri = f"file:{tmp_path / 'empty_mlruns'}"
    mlflow.set_tracking_uri(uri)
    summary = register_champion(
        tracking_uri=uri,
        experiment_name="does_not_exist",
        model_artifact="lightgbm_model",
        registered_model_name=MODEL_NAME,
        champion_alias="champion",
        champion_run_tag="pr05_champion_run_id",
    )
    assert summary["registry_strategy"] == STRATEGY_FALLBACK
    assert summary["champion"]["registered"] is False
    assert summary["warnings"]
