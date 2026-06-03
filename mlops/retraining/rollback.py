"""Rollback CLI logic: validate the manifest and perform a safe rollback.

Contract (AA-3):

* Default is a DRY RUN: it prints what would change and mutates nothing.
* An actual rollback requires an explicit confirm flag/env (``ROLLBACK_CONFIRM=
  true`` or ``--confirm``). It is never triggered by ``retrain-smoke`` or
  ``retraining-check``.
* No model versions are ever deleted. A post-rollback entry is appended to the
  manifest with timestamp + reason.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from mlops.retraining._io import now_utc, read_json, write_json
from mlops.retraining.config import RetrainingConfig
from mlops.retraining.summary import ROLLBACK_REQUIRED_FIELDS, validate_required_fields

logger = logging.getLogger(__name__)

DRY_RUN_BANNER = "DRY RUN — no changes made"


def manifest_path(cfg: RetrainingConfig) -> Path:
    return cfg.artifacts_dir / "rollback_manifest.json"


def validate_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    """Validate the rollback manifest schema; return a report."""

    missing = validate_required_fields(manifest, ROLLBACK_REQUIRED_FIELDS)
    has_target = manifest.get("rollback_target") is not None
    return {
        "valid": not missing and has_target,
        "missing_fields": missing,
        "has_rollback_target": has_target,
        "rollback_method": manifest.get("rollback_method"),
    }


def _confirm_requested(confirm_flag: bool) -> bool:
    if confirm_flag:
        return True
    return os.environ.get("ROLLBACK_CONFIRM", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def run_rollback(
    cfg: RetrainingConfig,
    *,
    confirm: bool = False,
    reason: str = "manual rollback request",
) -> dict[str, Any]:
    """Validate and (optionally) execute a rollback to the previous champion.

    Returns a structured report. With no confirmation this is a pure dry run.
    """

    path = manifest_path(cfg)
    report: dict[str, Any] = {
        "manifest_path": str(path),
        "dry_run": not _confirm_requested(confirm),
        "executed": False,
        "messages": [],
    }

    if not path.exists():
        report["messages"].append(
            f"No rollback manifest found at {path}. Run a retraining first "
            "(`make retrain-smoke`)."
        )
        report["valid"] = False
        return report

    manifest = read_json(path)
    validation = validate_manifest(manifest)
    report["validation"] = validation
    report["valid"] = validation["valid"]

    rollback_target = manifest.get("rollback_target")
    method = manifest.get("rollback_method")
    report["rollback_target"] = rollback_target
    report["rollback_method"] = method

    if not validation["valid"]:
        report["messages"].append(
            f"Rollback manifest invalid (missing {validation['missing_fields']} "
            "or no rollback target); refusing to act."
        )
        return report

    report["messages"].append(
        f"Rollback would point alias '{cfg.champion_alias}' of model "
        f"'{cfg.registered_model_name}' back to target: {rollback_target} "
        f"(method: {method})."
    )

    if report["dry_run"]:
        report["messages"].append(DRY_RUN_BANNER)
        if method == "manifest_only":
            report["messages"].append(
                "Rollback method is manifest_only: no MLflow alias exists to "
                "mutate. The manifest is the system of record."
            )
        return report

    # Confirmed, non-dry-run execution.
    if method == "manifest_only" or rollback_target is None:
        report["messages"].append(
            "Manifest-only rollback: recording the rollback intent; no registry "
            "alias mutation is possible/needed."
        )
        action = {"method": "manifest_only", "mutated": False}
    else:
        from mlops.retraining.registry_ops import rollback_to_previous

        action = rollback_to_previous(
            tracking_uri=cfg.tracking_uri,
            model_name=cfg.registered_model_name,
            champion_alias=cfg.champion_alias,
            rollback_target_version=str(rollback_target),
            dry_run=False,
        )
        report["messages"].extend(action.get("warnings", []))

    # Append a post-rollback history entry (never overwrite, never delete).
    history = list(manifest.get("history", []))
    history.append(
        {
            "event": "rollback_executed",
            "timestamp": now_utc(),
            "reason": reason,
            "target": rollback_target,
            "method": action.get("method"),
            "mutated": action.get("mutated", False),
            "champion_before_version": action.get("champion_before_version"),
            "champion_after_version": action.get("champion_after_version"),
        }
    )
    manifest["history"] = history
    write_json(path, manifest)

    report["executed"] = True
    report["action"] = action
    report["messages"].append(
        f"Rollback executed (method={action.get('method')}, "
        f"mutated={action.get('mutated', False)}). Recorded in manifest history."
    )
    return report
