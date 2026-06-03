"""Tests for PR-07 observability: health builder and Prometheus metrics."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from observability.artifacts import ARTIFACT_KEYS, ArtifactSpec
from observability.health import ALLOWED_DECISIONS, PR_STAGE, build_health_status

REQUIRED_HEALTH_KEYS = {
    "status",
    "pr_stage",
    "artifacts",
    "drift_detected",
    "bentoml_packaged",
    "champion_challenger_decision",
}


def _specs(root: Path) -> list[ArtifactSpec]:
    return [ArtifactSpec(key=key, path=root / f"{key}.json") for key in ARTIFACT_KEYS]


def test_health_unavailable_on_missing_paths():
    root = Path("/nonexistent/invforge-pr07")
    payload = build_health_status(
        specs=_specs(root),
        mlops_loop_path=root / "loop.json",
        comparison_path=root / "comparison.json",
        bentoml_path=root / "bento.json",
    )
    assert payload["status"] == "unavailable"
    assert REQUIRED_HEALTH_KEYS <= set(payload)
    assert payload["pr_stage"] == PR_STAGE
    assert payload["drift_detected"] is None
    assert payload["bentoml_packaged"] is None
    assert payload["champion_challenger_decision"] == "no_comparison"


def test_health_degraded_when_some_present(tmp_path):
    specs = _specs(tmp_path)
    specs[0].path.write_text("{}", encoding="utf-8")
    payload = build_health_status(
        specs=specs,
        mlops_loop_path=tmp_path / "loop.json",
        comparison_path=tmp_path / "comparison.json",
        bentoml_path=tmp_path / "bento.json",
    )
    assert payload["status"] == "degraded"
    assert payload["artifacts"][ARTIFACT_KEYS[0]] == "ok"
    assert payload["artifacts"][ARTIFACT_KEYS[1]] == "missing"


def test_health_ok_when_all_present(tmp_path):
    specs = _specs(tmp_path)
    for spec in specs:
        spec.path.write_text("{}", encoding="utf-8")
    loop = tmp_path / "loop.json"
    loop.write_text(
        json.dumps({"steps": {"evidently": {"dataset_drift_detected": True}}}),
        encoding="utf-8",
    )
    comparison = tmp_path / "comparison.json"
    comparison.write_text(json.dumps({"decision": "keep_champion"}), encoding="utf-8")
    bento = tmp_path / "bento.json"
    bento.write_text(json.dumps({"status": "packaged"}), encoding="utf-8")

    payload = build_health_status(
        specs=specs,
        mlops_loop_path=loop,
        comparison_path=comparison,
        bentoml_path=bento,
    )
    assert payload["status"] == "ok"
    assert payload["drift_detected"] is True
    assert payload["bentoml_packaged"] is True
    assert payload["champion_challenger_decision"] == "keep_champion"


def test_health_unknown_decision_for_invalid_value(tmp_path):
    comparison = tmp_path / "comparison.json"
    comparison.write_text(json.dumps({"decision": "lightgbm_v3"}), encoding="utf-8")
    payload = build_health_status(
        specs=_specs(tmp_path),
        mlops_loop_path=tmp_path / "loop.json",
        comparison_path=comparison,
        bentoml_path=tmp_path / "bento.json",
    )
    assert payload["champion_challenger_decision"] == "unknown"


def test_health_decision_values_allowed_set(tmp_path):
    for decision in ("promote_challenger", "keep_champion", "manual_review"):
        comparison = tmp_path / "comparison.json"
        comparison.write_text(json.dumps({"decision": decision}), encoding="utf-8")
        payload = build_health_status(
            specs=_specs(tmp_path),
            comparison_path=comparison,
            mlops_loop_path=tmp_path / "loop.json",
            bentoml_path=tmp_path / "bento.json",
        )
        assert payload["champion_challenger_decision"] == decision
        assert payload["champion_challenger_decision"] in ALLOWED_DECISIONS


def test_health_never_raises_on_corrupt_json(tmp_path):
    loop = tmp_path / "loop.json"
    loop.write_text("{not valid json", encoding="utf-8")
    payload = build_health_status(
        specs=_specs(tmp_path),
        mlops_loop_path=loop,
        comparison_path=tmp_path / "comparison.json",
        bentoml_path=tmp_path / "bento.json",
    )
    assert payload["drift_detected"] is None


def test_health_payload_contains_no_paths(tmp_path):
    specs = _specs(tmp_path)
    for spec in specs:
        spec.path.write_text("{}", encoding="utf-8")
    payload = build_health_status(specs=specs)
    text = json.dumps(payload)
    assert "/" not in text
    assert "\\" not in text
    assert str(tmp_path) not in text


def test_metric_names_registered():
    pytest.importorskip("prometheus_client")
    from observability import metrics as metrics_mod

    registered = metrics_mod.registered_metric_names()
    for name in metrics_mod.METRIC_NAMES:
        assert name in registered


def test_metrics_have_no_path_label_values(tmp_path):
    pytest.importorskip("prometheus_client")
    from observability import metrics as metrics_mod

    specs = _specs(tmp_path)
    for spec in specs:
        spec.path.write_text("{}", encoding="utf-8")
    metrics_mod.refresh_artifact_metrics(
        specs=specs,
        mlops_loop_path=tmp_path / "loop.json",
        comparison_path=tmp_path / "comparison.json",
        bentoml_path=tmp_path / "bento.json",
    )
    assert metrics_mod.assert_no_path_label_values() == []


def test_metrics_render_returns_prometheus_bytes():
    pytest.importorskip("prometheus_client")
    from observability import metrics as metrics_mod

    payload, content_type = metrics_mod.render_latest()
    assert isinstance(payload, bytes)
    assert b"invforge_service_info" in payload
    assert "text/plain" in content_type


def test_drift_gauge_encodes_unknown_as_minus_one(tmp_path):
    pytest.importorskip("prometheus_client")
    from observability import metrics as metrics_mod

    metrics_mod.refresh_artifact_metrics(
        specs=_specs(tmp_path),
        mlops_loop_path=tmp_path / "missing-loop.json",
        comparison_path=tmp_path / "missing.json",
        bentoml_path=tmp_path / "missing-bento.json",
    )
    assert metrics_mod.DRIFT_DETECTED._value.get() == metrics_mod.UNKNOWN


def test_champion_challenger_decision_one_hot(tmp_path):
    pytest.importorskip("prometheus_client")
    from observability import metrics as metrics_mod

    comparison = tmp_path / "comparison.json"
    comparison.write_text(
        json.dumps({"decision": "promote_challenger"}), encoding="utf-8"
    )
    metrics_mod.refresh_artifact_metrics(
        specs=_specs(tmp_path),
        comparison_path=comparison,
        mlops_loop_path=tmp_path / "loop.json",
        bentoml_path=tmp_path / "bento.json",
    )
    active = metrics_mod.CHAMPION_CHALLENGER_DECISION.labels(
        decision="promote_challenger"
    )._value.get()
    other = metrics_mod.CHAMPION_CHALLENGER_DECISION.labels(
        decision="keep_champion"
    )._value.get()
    assert active == 1
    assert other == 0
