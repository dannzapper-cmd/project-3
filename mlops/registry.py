"""MLflow model registry / metadata for the current demand forecasting model.

Strategy (chosen and committed): **native MLflow Model Registry with aliases**
(``registry_strategy = "native_aliases"``). MLflow 3.x supports registering
models and assigning aliases against the local file store used by this repo,
without any additional running service.

If native registration fails for any reason (no run found, registry call
errors, etc.) the code falls back to **tags + a local JSON summary**
(``registry_strategy = "tags_json_fallback"``) and records why. Either way a
``registered_model_summary.json`` is produced and is honest about the local
file-store limitations.

Idempotency: before registering a new version, existing versions are checked
for one whose source run id matches (via the configured run tag or the
version's own ``run_id``). If found, registration is skipped and the existing
version is reused.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

STRATEGY_NATIVE = "native_aliases"
STRATEGY_FALLBACK = "tags_json_fallback"

LIMITATIONS = [
    "Local MLflow file-store registry: no central server, authentication, "
    "stage transitions audit, or multi-user governance.",
    "The mlruns/ tracking store is regenerated locally and is not committed to "
    "git, so registry state is ephemeral per machine.",
    "Models are trained on synthetic data; registry metadata does not imply "
    "production readiness.",
]


def _model_tags() -> dict[str, str]:
    return {
        "scope": "pr05",
        "data_source": "synthetic",
        "production_ready": "false",
        "managed_by": "invforge_mlops_loop",
    }


def _find_existing_version(
    client: Any,
    model_name: str,
    run_id: str,
    run_tag: str,
) -> Any | None:
    """Return an existing model version mapped to ``run_id`` if present."""

    try:
        versions = client.search_model_versions(f"name='{model_name}'")
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Could not search model versions: %s", exc)
        return None

    for version in versions:
        tags = getattr(version, "tags", {}) or {}
        if tags.get(run_tag) == run_id:
            return version
        if getattr(version, "run_id", None) == run_id:
            return version
    return None


def _model_signature(model_uri: str) -> dict[str, Any]:
    """Best-effort read of the logged model signature / input example."""

    try:
        from mlflow.models import get_model_info

        info = get_model_info(model_uri)
        signature = info.signature
        return {
            "signature_logged": signature is not None,
            "signature": signature.to_dict() if signature is not None else None,
            "input_example_logged": bool(
                getattr(info, "saved_input_example_info", None)
            ),
        }
    except Exception as exc:  # pragma: no cover - depends on stored model
        return {
            "signature_logged": False,
            "signature": None,
            "input_example_logged": False,
            "signature_read_error": f"{type(exc).__name__}: {exc}",
        }


def register_champion(
    *,
    tracking_uri: str,
    experiment_name: str,
    model_artifact: str,
    registered_model_name: str,
    champion_alias: str,
    champion_run_tag: str,
) -> dict[str, Any]:
    """Register the latest forecasting run's model and assign the champion alias.

    Returns a stable summary dict. Falls back to a tags/JSON-only summary when
    native registration is not possible.
    """

    import mlflow
    from mlflow.tracking import MlflowClient

    mlflow.set_tracking_uri(tracking_uri)
    client = MlflowClient(tracking_uri=tracking_uri)

    base_summary: dict[str, Any] = {
        "registry_strategy": STRATEGY_NATIVE,
        "model_name": registered_model_name,
        "tracking_uri": tracking_uri,
        "source_experiment": experiment_name,
        "champion_alias": champion_alias,
        "model_tags": _model_tags(),
        "limitations": list(LIMITATIONS),
        "warnings": [],
    }

    experiment = client.get_experiment_by_name(experiment_name)
    if experiment is None:
        base_summary.update(
            registry_strategy=STRATEGY_FALLBACK,
            champion={"registered": False},
            idempotency={"action": "skipped", "note": "no experiment found"},
        )
        base_summary["warnings"].append(
            f"Experiment '{experiment_name}' not found in {tracking_uri}; run "
            "`make train-ml` first. Wrote JSON-only fallback summary."
        )
        return base_summary

    runs = client.search_runs(
        [experiment.experiment_id],
        order_by=["attributes.start_time DESC"],
        max_results=1,
    )
    if not runs:
        base_summary.update(
            registry_strategy=STRATEGY_FALLBACK,
            champion={"registered": False},
            idempotency={"action": "skipped", "note": "no runs found"},
        )
        base_summary["warnings"].append(
            "No runs found in the forecast experiment; wrote JSON-only fallback "
            "summary."
        )
        return base_summary

    run = runs[0]
    run_id = run.info.run_id
    model_uri = f"runs:/{run_id}/{model_artifact}"
    signature_info = _model_signature(model_uri)

    try:
        existing = _find_existing_version(
            client, registered_model_name, run_id, champion_run_tag
        )
        if existing is not None:
            version = existing.version
            action = "skipped_existing"
            note = (
                f"Version {version} already maps to run {run_id}; registration "
                "skipped (idempotent)."
            )
            logger.warning(note)
        else:
            model_version = mlflow.register_model(model_uri, registered_model_name)
            version = model_version.version
            action = "registered_new_version"
            note = f"Registered version {version} from run {run_id}."

        for key, value in _model_tags().items():
            client.set_model_version_tag(
                registered_model_name, version, key, value
            )
        client.set_model_version_tag(
            registered_model_name, version, champion_run_tag, run_id
        )
        client.set_registered_model_alias(
            registered_model_name, champion_alias, version
        )

        base_summary.update(
            registry_strategy=STRATEGY_NATIVE,
            champion={
                "registered": True,
                "version": str(version),
                "run_id": run_id,
                "alias": champion_alias,
                "source_model_uri": model_uri,
                "tags": {**_model_tags(), champion_run_tag: run_id},
                "params": dict(run.data.params),
                "metrics": dict(run.data.metrics),
                "artifact_references": {
                    "model_uri": model_uri,
                    "run_artifact_uri": run.info.artifact_uri,
                },
                **signature_info,
            },
            idempotency={"action": action, "note": note},
        )
        return base_summary
    except Exception as exc:
        logger.warning("Native MLflow registration failed: %s", exc)
        base_summary.update(
            registry_strategy=STRATEGY_FALLBACK,
            champion={
                "registered": False,
                "run_id": run_id,
                "source_model_uri": model_uri,
                "intended_tags": {**_model_tags(), champion_run_tag: run_id},
                "params": dict(run.data.params),
                "metrics": dict(run.data.metrics),
                **signature_info,
            },
            idempotency={"action": "fallback", "note": "json summary only"},
        )
        base_summary["warnings"].append(
            f"Native registry/alias call failed ({type(exc).__name__}: {exc}); "
            "fell back to tags + JSON summary."
        )
        return base_summary
