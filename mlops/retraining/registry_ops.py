"""Safe MLflow model-registry operations for retraining promotion + rollback.

Hard rules (AA-2):

* Reuse the PR-05 registry conventions exactly (registered model name, the
  ``champion`` alias, version tags).
* NEVER call ``delete_model_version``, ``delete_registered_model``, or
  ``delete_run``. There are no destructive operations in this module.
* Before overwriting the ``champion`` alias, the current champion version is
  recorded under the ``previous_champion`` alias so rollback always has a
  target.
* If native registry/alias mutation is unavailable (file-store quirk, no run,
  call error), the caller falls back to a manifest-only rollback path.

All registry mutation is "controlled": it only happens after the promotion gate
has passed, and the previous champion is always preserved first.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

CANDIDATE_TAGS = {
    "scope": "pr09",
    "data_source": "synthetic",
    "production_ready": "false",
    "managed_by": "invforge_retraining",
}


def _client(tracking_uri: str):
    import mlflow
    from mlflow.tracking import MlflowClient

    mlflow.set_tracking_uri(tracking_uri)
    return MlflowClient(tracking_uri=tracking_uri)


def get_alias_version(
    client: Any, model_name: str, alias: str
) -> str | None:
    """Return the version a registry alias points to, or ``None``."""

    try:
        mv = client.get_model_version_by_alias(model_name, alias)
    except Exception:
        return None
    return getattr(mv, "version", None)


def load_champion(
    *,
    tracking_uri: str,
    model_name: str,
    champion_alias: str,
    forecast_experiment: str,
    model_artifact: str,
) -> dict[str, Any]:
    """Locate the current champion model.

    Preference order:

    1. Registry alias ``models:/<model_name>@<champion_alias>`` (PR-05 native).
    2. Latest run in the PR-03 forecast experiment (bootstrap only).

    Returns a dict describing the champion (which may be empty when none
    exists). It never trains or mutates anything.
    """

    info: dict[str, Any] = {
        "available": False,
        "source": None,
        "version": None,
        "run_id": None,
        "model_uri": None,
        "alias": champion_alias,
        "logged_metrics": {},
        "warnings": [],
    }
    try:
        client = _client(tracking_uri)
    except Exception as exc:  # pragma: no cover - import/connection guard
        info["warnings"].append(f"MLflow client unavailable: {exc}")
        return info

    version = get_alias_version(client, model_name, champion_alias)
    if version is not None:
        try:
            mv = client.get_model_version(model_name, version)
            run_id = getattr(mv, "run_id", None)
            info.update(
                available=True,
                source="registry_alias",
                version=str(version),
                run_id=run_id,
                model_uri=f"models:/{model_name}@{champion_alias}",
            )
            if run_id:
                run = client.get_run(run_id)
                info["logged_metrics"] = dict(run.data.metrics)
            return info
        except Exception as exc:
            info["warnings"].append(
                f"Champion alias '{champion_alias}' present but unreadable: {exc}"
            )

    # Bootstrap fallback: latest forecast run (no alias yet).
    try:
        experiment = client.get_experiment_by_name(forecast_experiment)
        if experiment is None:
            info["warnings"].append(
                f"No champion alias and forecast experiment "
                f"'{forecast_experiment}' not found."
            )
            return info
        runs = client.search_runs(
            [experiment.experiment_id],
            order_by=["attributes.start_time DESC"],
            max_results=1,
        )
        if not runs:
            info["warnings"].append("No champion alias and no forecast runs found.")
            return info
        run = runs[0]
        info.update(
            available=True,
            source="forecast_experiment_latest_run",
            run_id=run.info.run_id,
            model_uri=f"runs:/{run.info.run_id}/{model_artifact}",
            logged_metrics=dict(run.data.metrics),
        )
    except Exception as exc:
        info["warnings"].append(f"Could not bootstrap champion from runs: {exc}")
    return info


def promote_candidate(
    *,
    tracking_uri: str,
    model_name: str,
    candidate_run_id: str,
    model_artifact: str,
    champion_alias: str,
    previous_champion_alias: str,
    candidate_tag: str,
) -> dict[str, Any]:
    """Register the candidate and point the champion alias at it (controlled).

    Before the champion alias is moved, the current champion version is saved
    under ``previous_champion_alias`` so rollback always has a target. No
    version is ever deleted. On any failure, returns ``method = "manifest_only"``
    so the caller writes a manifest-only rollback path instead.
    """

    result: dict[str, Any] = {
        "method": "mlflow_alias",
        "registered": False,
        "candidate_version": None,
        "previous_champion_version": None,
        "champion_alias": champion_alias,
        "previous_champion_alias": previous_champion_alias,
        "warnings": [],
    }
    candidate_uri = f"runs:/{candidate_run_id}/{model_artifact}"
    try:
        import mlflow

        client = _client(tracking_uri)

        previous_version = get_alias_version(client, model_name, champion_alias)
        result["previous_champion_version"] = previous_version

        model_version = mlflow.register_model(candidate_uri, model_name)
        candidate_version = model_version.version
        result["candidate_version"] = str(candidate_version)

        for key, value in CANDIDATE_TAGS.items():
            client.set_model_version_tag(model_name, candidate_version, key, value)
        client.set_model_version_tag(
            model_name, candidate_version, candidate_tag, candidate_run_id
        )

        # Preserve the outgoing champion before overwriting the alias.
        if previous_version is not None and previous_version != str(candidate_version):
            client.set_registered_model_alias(
                model_name, previous_champion_alias, previous_version
            )

        client.set_registered_model_alias(
            model_name, champion_alias, candidate_version
        )
        result["registered"] = True
        return result
    except Exception as exc:
        logger.warning("Native MLflow promotion failed: %s", exc)
        result.update(
            method="manifest_only",
            warnings=[
                f"Native registry/alias promotion failed ({type(exc).__name__}: "
                f"{exc}); falling back to a manifest-only rollback record."
            ],
        )
        return result


def rollback_to_previous(
    *,
    tracking_uri: str,
    model_name: str,
    champion_alias: str,
    rollback_target_version: str,
    dry_run: bool,
) -> dict[str, Any]:
    """Point the champion alias back at a previous version (controlled).

    With ``dry_run=True`` nothing is mutated. No version is ever deleted.
    """

    result: dict[str, Any] = {
        "method": "mlflow_alias",
        "dry_run": dry_run,
        "model_name": model_name,
        "champion_alias": champion_alias,
        "target_version": rollback_target_version,
        "champion_before_version": None,
        "champion_after_version": None,
        "mutated": False,
        "warnings": [],
    }
    try:
        client = _client(tracking_uri)
        result["champion_before_version"] = get_alias_version(
            client, model_name, champion_alias
        )
        if dry_run:
            result["champion_after_version"] = result["champion_before_version"]
            return result
        client.set_registered_model_alias(
            model_name, champion_alias, rollback_target_version
        )
        result["champion_after_version"] = rollback_target_version
        result["mutated"] = True
        return result
    except Exception as exc:
        logger.warning("MLflow rollback failed: %s", exc)
        result.update(
            method="manifest_only",
            warnings=[
                f"Native alias rollback failed ({type(exc).__name__}: {exc}); "
                "no registry change made. Use the rollback manifest as the "
                "system of record."
            ],
        )
        return result
