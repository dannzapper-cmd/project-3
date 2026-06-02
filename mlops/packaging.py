"""Minimal, optional BentoML packaging of the champion forecasting model.

Scope (per PR-05 spec): package the champion/current model into the local
BentoML model store only. No ``bentoml build``, no Docker image, no serving
deployment, no BentoCloud, no Kubernetes. The local model store lives outside
the repository (``~/bentoml``) and is never committed.

BentoML is imported lazily. If it is not installed, conflicts, or packaging
fails at runtime, this module records a clear ``deferred`` status instead of
raising, so the rest of the MLOps loop still completes.

Idempotency: before saving, the local store is checked for a model carrying
the same ``mlflow_run_id`` label. If found, saving is skipped.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Per PR-05 addendum patch 1: serving/deployment belongs to later PRs.
DEFERRED_TO = "PR-10 or PR-11"

WARNINGS = [
    "Local BentoML model store only; no Docker image, serving deployment, or "
    "Kubernetes (those belong to later PRs).",
    "Champion model is trained on synthetic data and is not production ready.",
]


def _existing_model(bentoml: Any, model_name: str, run_id: str) -> Any | None:
    try:
        for model in bentoml.models.list():
            if model.tag.name != model_name:
                continue
            labels = getattr(model.info, "labels", {}) or {}
            if labels.get("mlflow_run_id") == run_id:
                return model
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Could not list BentoML models: %s", exc)
    return None


def _deferred(reason: str, *, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    summary = {
        "status": "deferred",
        "reason": reason,
        "deferred_to": DEFERRED_TO,
        "warning": "BentoML packaging deferred to avoid dependency mutation",
        "warnings": list(WARNINGS),
    }
    if extra:
        summary.update(extra)
    return summary


def package_champion(
    *,
    tracking_uri: str,
    experiment_name: str,
    model_artifact: str,
    model_name: str,
) -> dict[str, Any]:
    """Save the champion model to the local BentoML store; return a summary."""

    try:
        import bentoml
    except ImportError as exc:
        return _deferred(f"BentoML not installed: {exc}")
    except Exception as exc:  # pragma: no cover - import-time conflict
        return _deferred(f"BentoML import failed: {type(exc).__name__}: {exc}")

    try:
        import mlflow
        from mlflow.tracking import MlflowClient

        mlflow.set_tracking_uri(tracking_uri)
        client = MlflowClient(tracking_uri=tracking_uri)
        experiment = client.get_experiment_by_name(experiment_name)
        if experiment is None:
            return {
                "status": "skipped",
                "reason": (
                    f"Forecast experiment '{experiment_name}' not found; run "
                    "`make train-ml` first."
                ),
                "warnings": list(WARNINGS),
            }
        runs = client.search_runs(
            [experiment.experiment_id],
            order_by=["attributes.start_time DESC"],
            max_results=1,
        )
        if not runs:
            return {
                "status": "skipped",
                "reason": "No forecast runs found to package.",
                "warnings": list(WARNINGS),
            }

        run = runs[0]
        run_id = run.info.run_id
        model_uri = f"runs:/{run_id}/{model_artifact}"

        existing = _existing_model(bentoml, model_name, run_id)
        if existing is not None:
            return {
                "status": "packaged",
                "action": "skipped_existing",
                "bentoml_version": getattr(bentoml, "__version__", "unknown"),
                "model_tag": str(existing.tag),
                "mlflow_run_id": run_id,
                "source_model_uri": model_uri,
                "note": (
                    "Model with this mlflow_run_id already exists in the local "
                    "store; save skipped (idempotent)."
                ),
                "warnings": list(WARNINGS),
            }

        model = mlflow.lightgbm.load_model(model_uri)
        labels = {
            "mlflow_run_id": run_id,
            "scope": "pr05",
            "data_source": "synthetic",
            "production_ready": "false",
        }
        metadata = {
            "framework": "lightgbm",
            "source_model_uri": model_uri,
            "champion": True,
            "warning": "Synthetic-data champion model; not production ready.",
        }
        saved = _save_model(bentoml, model, model_name, labels, metadata)

        return {
            "status": "packaged",
            "action": "saved_new_version",
            "bentoml_version": getattr(bentoml, "__version__", "unknown"),
            "framework_api": saved["framework_api"],
            "model_tag": saved["tag"],
            "mlflow_run_id": run_id,
            "source_model_uri": model_uri,
            "labels": labels,
            "metadata": metadata,
            "note": (
                "Saved to the local BentoML model store only. No bentoml build, "
                "Docker image, or deployment was produced."
            ),
            "warnings": list(WARNINGS),
        }
    except Exception as exc:
        logger.warning("BentoML packaging failed: %s", exc)
        return _deferred(
            f"Packaging failed at runtime: {type(exc).__name__}: {exc}",
        )


def _save_model(
    bentoml: Any,
    model: Any,
    model_name: str,
    labels: dict[str, str],
    metadata: dict[str, Any],
) -> dict[str, str]:
    """Save ``model`` using the most appropriate BentoML framework API."""

    signatures = {"predict": {"batchable": True}}

    # LightGBM sklearn wrapper -> bentoml.sklearn; raw Booster -> bentoml.lightgbm.
    try:
        import lightgbm as lgb

        if isinstance(model, lgb.basic.Booster):
            saved = bentoml.lightgbm.save_model(
                model_name,
                model,
                signatures=signatures,
                labels=labels,
                metadata=metadata,
            )
            return {"tag": str(saved.tag), "framework_api": "bentoml.lightgbm"}
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("lightgbm framework save unavailable: %s", exc)

    if hasattr(model, "predict"):
        saved = bentoml.sklearn.save_model(
            model_name,
            model,
            signatures=signatures,
            labels=labels,
            metadata=metadata,
        )
        return {"tag": str(saved.tag), "framework_api": "bentoml.sklearn"}

    saved = bentoml.picklable_model.save_model(
        model_name,
        model,
        signatures=signatures,
        labels=labels,
        metadata=metadata,
    )
    return {"tag": str(saved.tag), "framework_api": "bentoml.picklable_model"}
