"""Smoke and MLflow integration tests for training pipeline."""

from __future__ import annotations

import time
from pathlib import Path

import mlflow
import pytest
import yaml

from ml.train import run_training


@pytest.fixture
def ml_config(tmp_path, synthetic_dir, monkeypatch) -> dict:
    monkeypatch.setenv("MLFLOW_ALLOW_FILE_STORE", "true")
    base = yaml.safe_load(Path("ml/config.yaml").read_text(encoding="utf-8"))
    base["data"]["synthetic_dir"] = str(synthetic_dir)
    base["mlflow"]["tracking_uri"] = str(tmp_path / "mlruns")
    base["lightgbm"]["n_estimators"] = 50
    return base


def test_smoke_train_under_60_seconds(ml_config):
    start = time.monotonic()
    results = run_training(ml_config, max_items=10, max_days=30)
    elapsed = time.monotonic() - start

    assert elapsed < 60, f"Smoke training took {elapsed:.1f}s (limit 60s)"
    assert "lightgbm" in results
    assert "statsforecast" in results
    assert results["lightgbm"]["mae"] >= 0


def test_mlflow_run_logs_mae(ml_config):
    tracking_uri = ml_config["mlflow"]["tracking_uri"]
    results = run_training(ml_config, max_items=10, max_days=30)

    run_id = results["run_id"]
    assert run_id is not None

    mlflow.set_tracking_uri(tracking_uri)
    run = mlflow.get_run(run_id)
    assert "lightgbm_mae" in run.data.metrics
    assert run.data.metrics["lightgbm_mae"] >= 0
