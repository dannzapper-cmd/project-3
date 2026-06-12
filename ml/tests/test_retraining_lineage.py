"""Tests for the optional OpenLineage emission wrapper (PR-11B).

Validates the two senior-critical invariants:

1. **Disabled by default**: with OPENLINEAGE_URL unset, every emit_* is a no-op
   and returns False (so the default retrain path is unchanged).
2. **Real events when enabled**: with OPENLINEAGE_URL set, emit_start/complete/
   fail build genuine OpenLineage RunEvents and hand them to a client. We capture
   them with a recording client (no network/Marquez needed) and assert the event
   types and job identity. This is the "emission validated by a local smoke"
   required to claim lineage emission is real.

The OpenLineage RunEvent objects are real, so this test requires
``openlineage-python`` (retraining group); it is skipped if not installed.
"""

from __future__ import annotations

import pytest

from mlops.retraining import lineage

pytest.importorskip("openlineage.client")


class _RecordingClient:
    def __init__(self) -> None:
        self.events: list[object] = []

    def emit(self, event: object) -> None:
        self.events.append(event)


def test_disabled_when_no_url(monkeypatch):
    monkeypatch.delenv("OPENLINEAGE_URL", raising=False)
    assert lineage.lineage_enabled() is False
    assert lineage.emit_start("run-1") is False
    assert lineage.emit_complete("run-1") is False
    assert lineage.emit_fail("run-1") is False


def test_emits_real_start_and_complete(monkeypatch):
    monkeypatch.setenv("OPENLINEAGE_URL", "http://localhost:5000")
    recorder = _RecordingClient()
    monkeypatch.setattr(lineage, "_build_client", lambda: recorder)

    run_id = lineage.new_run_id()
    assert lineage.emit_start(run_id) is True
    assert lineage.emit_complete(run_id) is True

    assert len(recorder.events) == 2
    start, complete = recorder.events
    assert start.eventType.name == "START"
    assert complete.eventType.name == "COMPLETE"
    # Same run id and the fixed job identity.
    assert start.run.runId == run_id
    assert start.job.name == "invforge.retraining"
    assert start.job.namespace == "invforge"


def test_emit_never_raises_on_client_error(monkeypatch):
    monkeypatch.setenv("OPENLINEAGE_URL", "http://localhost:5000")

    def _boom():
        raise RuntimeError("connection refused")

    monkeypatch.setattr(lineage, "_build_client", _boom)
    # Failure to emit must degrade to False, never propagate.
    assert lineage.emit_start("run-x") is False
