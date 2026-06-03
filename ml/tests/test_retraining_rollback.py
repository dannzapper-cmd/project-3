"""Tests for the safe rollback path (dry-run default, no destructive ops)."""

from __future__ import annotations

import dataclasses
import json

from mlops.retraining._io import read_json
from mlops.retraining.config import load_retraining_config
from mlops.retraining.rollback import run_rollback, validate_manifest
from mlops.retraining.summary import build_rollback_manifest


def _cfg(tmp_path):
    cfg = load_retraining_config(mode="smoke")
    return dataclasses.replace(
        cfg, artifacts_dir=tmp_path, tracking_uri=str(tmp_path / "mlruns")
    )


def _write_manifest(tmp_path, **overrides):
    manifest = build_rollback_manifest(
        champion_before={"version": "2"},
        champion_after={"version": "3"},
        candidate_run_id="run3",
        rollback_target="2",
        rollback_method="manifest_only",
        metrics_before={"mae": 2.0},
        metrics_after={"mae": 1.9},
    )
    manifest.update(overrides)
    path = tmp_path / "rollback_manifest.json"
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return path


def test_validate_manifest_detects_missing_target():
    manifest = build_rollback_manifest(
        champion_before=None,
        champion_after=None,
        candidate_run_id=None,
        rollback_target=None,
        rollback_method="manifest_only",
        metrics_before=None,
        metrics_after=None,
    )
    report = validate_manifest(manifest)
    assert report["has_rollback_target"] is False
    assert report["valid"] is False


def test_dry_run_is_default_and_mutates_nothing(tmp_path):
    path = _write_manifest(tmp_path)
    before = path.read_bytes()
    cfg = _cfg(tmp_path)

    report = run_rollback(cfg, confirm=False)

    assert report["dry_run"] is True
    assert report["executed"] is False
    assert report["valid"] is True
    # Manifest is byte-for-byte unchanged in a dry run.
    assert path.read_bytes() == before


def test_missing_manifest_is_invalid(tmp_path):
    cfg = _cfg(tmp_path)
    report = run_rollback(cfg, confirm=False)
    assert report["valid"] is False
    assert report["executed"] is False


def test_confirmed_manifest_only_rollback_appends_history(tmp_path):
    _write_manifest(tmp_path)
    cfg = _cfg(tmp_path)

    report = run_rollback(cfg, confirm=True, reason="unit test rollback")

    assert report["dry_run"] is False
    assert report["executed"] is True
    manifest = read_json(tmp_path / "rollback_manifest.json")
    assert manifest["history"], "rollback should append a history entry"
    last = manifest["history"][-1]
    assert last["event"] == "rollback_executed"
    assert last["reason"] == "unit test rollback"
    # manifest_only path never claims to have mutated a registry.
    assert last["mutated"] is False


def test_env_confirm_triggers_execution(tmp_path, monkeypatch):
    _write_manifest(tmp_path)
    cfg = _cfg(tmp_path)
    monkeypatch.setenv("ROLLBACK_CONFIRM", "true")
    report = run_rollback(cfg, confirm=False)
    assert report["dry_run"] is False
    assert report["executed"] is True
