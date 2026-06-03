"""Behavioral tests for the retraining finalize logic + safety invariants.

These exercise the promotion/rejection/failure bookkeeping in
``finalize_and_write`` without running the full ZenML pipeline (kept fast, and
no ZenML import is required), plus a guard that the registry-ops module makes no
destructive MLflow calls.
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
import json

from mlops.retraining import registry_ops
from mlops.retraining.config import load_retraining_config
from mlops.retraining.gate import (
    STATUS_FAILED,
    STATUS_PROMOTED,
    STATUS_REJECTED,
)
from mlops.retraining.lifecycle import finalize_and_write
from mlops.retraining.summary import (
    ROLLBACK_REQUIRED_FIELDS,
    SUMMARY_REQUIRED_FIELDS,
    validate_required_fields,
)

CHAMPION = {
    "available": True,
    "source": "registry_alias",
    "version": "1",
    "run_id": "champ_run",
    "model_uri": "models:/demand_forecast@champion",
}


def _cfg(tmp_path):
    cfg = load_retraining_config(mode="smoke")
    return dataclasses.replace(
        cfg, artifacts_dir=tmp_path, tracking_uri=str(tmp_path / "mlruns")
    )


def _comparison(candidate, champion, *, promoted, delta=None, rel=None):
    return {
        "candidate_metric": candidate,
        "champion_metric": champion,
        "metric_direction": "lower_is_better",
        "absolute_delta": delta,
        "relative_delta_pct": rel,
        "promotion_threshold": 5.0,
        "promoted": promoted,
    }


def test_rejected_candidate_leaves_champion_unchanged(tmp_path):
    cfg = _cfg(tmp_path)
    gate = {
        "status": STATUS_REJECTED,
        "promoted": False,
        "first_run": False,
        "reason": "candidate worse",
        "comparison": _comparison(2.5, 2.0, promoted=False, delta=0.5, rel=-25.0),
    }
    candidate = {
        "run_id": "cand_run",
        "metrics": {"mae": 2.5},
        "champion_metrics": {"mae": 2.0},
        "tuning": {"enabled": False},
        "data_reference": {"rows": 10},
    }
    # Candidate was not promoted, so promotion did not register anything.
    promotion = {"method": "mlflow_alias", "registered": False}

    summary = finalize_and_write(
        cfg, candidate, CHAMPION, gate, promotion, {"passed": True}
    )

    assert summary["status"] == STATUS_REJECTED
    assert summary["promoted"] is False
    assert summary["rejected_reason"] == "candidate worse"
    # Champion is unchanged: before == after, rollback target is the champion.
    assert summary["champion_after"] == summary["champion_before"]
    assert summary["rollback_target"] == "1"
    assert validate_required_fields(summary, SUMMARY_REQUIRED_FIELDS) == []


def test_promoted_candidate_records_rollback_target(tmp_path):
    cfg = _cfg(tmp_path)
    gate = {
        "status": STATUS_PROMOTED,
        "promoted": True,
        "first_run": False,
        "reason": "candidate better",
        "comparison": _comparison(1.5, 2.0, promoted=True, delta=-0.5, rel=25.0),
    }
    candidate = {
        "run_id": "cand_run",
        "metrics": {"mae": 1.5},
        "champion_metrics": {"mae": 2.0},
        "tuning": {"enabled": False},
        "data_reference": {"rows": 10},
    }
    promotion = {
        "method": "mlflow_alias",
        "registered": True,
        "candidate_version": "2",
        "previous_champion_version": "1",
    }

    summary = finalize_and_write(
        cfg, candidate, CHAMPION, gate, promotion, {"passed": True}
    )

    assert summary["promoted"] is True
    assert summary["champion_after"]["version"] == "2"
    # After a promotion, the previous champion is the identifiable rollback target.
    assert summary["rollback_target"] == "1"


def test_failed_run_preserves_champion_and_writes_failed_status(tmp_path):
    cfg = _cfg(tmp_path)
    gate = {
        "status": STATUS_FAILED,
        "promoted": False,
        "first_run": False,
        "comparison": _comparison(None, None, promoted=False),
    }
    candidate = {
        "run_id": None,
        "metrics": {},
        "champion_metrics": {"mae": 2.0},
        "tuning": {"enabled": False},
        "data_reference": None,
    }
    promotion = {"method": "manifest_only", "registered": False}

    summary = finalize_and_write(
        cfg,
        candidate,
        CHAMPION,
        gate,
        promotion,
        {"passed": False},
        failure_reason="training exploded",
    )

    assert summary["status"] == STATUS_FAILED
    assert summary["promoted"] is False
    assert summary["failure_reason"] == "training exploded"
    # Champion reference is unchanged in the rollback manifest.
    manifest = json.loads(
        (tmp_path / "rollback_manifest.json").read_text(encoding="utf-8")
    )
    assert validate_required_fields(manifest, ROLLBACK_REQUIRED_FIELDS) == []
    assert manifest["champion_before"] == manifest["champion_after"]


def test_registry_ops_have_no_destructive_calls():
    """Parse the AST: no actual delete_* calls (docstrings/comments excluded)."""

    forbidden = {
        "delete_model_version",
        "delete_registered_model",
        "delete_run",
        "delete_experiment",
    }
    tree = ast.parse(inspect.getsource(registry_ops))
    called = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert forbidden.isdisjoint(called), (
        f"destructive call found: {forbidden & called}"
    )
