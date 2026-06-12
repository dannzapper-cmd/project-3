"""Optional OpenLineage emission for the retraining pipeline (PR-11B).

This is a thin, ENV-GATED wrapper — not a refactor. It emits OpenLineage
``START`` / ``COMPLETE`` / ``FAIL`` run events for the retraining job so a local
Marquez instance can show the job/run lineage.

Hard guarantees:

* **No-op by default.** If ``OPENLINEAGE_URL`` is unset, every function returns
  ``False`` and does nothing. The default ``make retrain-smoke`` / CI behavior is
  therefore completely unchanged.
* **Never raises.** Any import error, version mismatch, or transport failure is
  caught and logged at warning level; retraining is never broken by lineage.
* **No new required dependency at import time.** ``openlineage-python`` is
  imported lazily inside the emit path only.

Enable locally by pointing at Marquez (see docs/runbooks/lineage-inspection.md):

    export OPENLINEAGE_URL=http://localhost:5000
    make retrain-smoke
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

PRODUCER = "https://github.com/dannzapper-cmd/invforge/tree/main/mlops/retraining"
DEFAULT_NAMESPACE = "invforge"
JOB_NAME = "invforge.retraining"


def lineage_enabled() -> bool:
    """True only when an OpenLineage endpoint is configured."""

    return bool(os.environ.get("OPENLINEAGE_URL"))


def namespace() -> str:
    return os.environ.get("OPENLINEAGE_NAMESPACE", DEFAULT_NAMESPACE)


def new_run_id() -> str:
    """A fresh UUID run id for one retraining run."""

    return str(uuid.uuid4())


def _build_client() -> Any:
    """Construct an OpenLineage client from the environment (lazy import)."""

    from openlineage.client import OpenLineageClient

    try:
        return OpenLineageClient.from_environment()
    except Exception:  # pragma: no cover - older/newer client signature
        return OpenLineageClient(url=os.environ["OPENLINEAGE_URL"])


def _run_types() -> tuple[Any, Any, Any, Any]:
    """Return (Run, Job, RunEvent, RunState) across OpenLineage client versions."""

    try:
        from openlineage.client.event_v2 import Job, Run, RunEvent, RunState

        return Run, Job, RunEvent, RunState
    except Exception:  # pragma: no cover - fall back to the classic run module
        from openlineage.client.run import Job, Run, RunEvent, RunState

        return Run, Job, RunEvent, RunState


def _emit(state_name: str, run_id: str) -> bool:
    if not lineage_enabled():
        return False
    try:
        run_cls, job_cls, event_cls, state_cls = _run_types()
        client = _build_client()
        event = event_cls(
            eventType=getattr(state_cls, state_name),
            eventTime=datetime.now(timezone.utc).isoformat(),
            run=run_cls(runId=run_id),
            job=job_cls(namespace=namespace(), name=JOB_NAME),
            producer=PRODUCER,
            inputs=[],
            outputs=[],
        )
        client.emit(event)
        logger.info("openlineage_event_emitted state=%s run=%s", state_name, run_id)
        return True
    except Exception as exc:  # never break retraining because of lineage
        logger.warning("OpenLineage emission skipped (%s): %s", state_name, exc)
        return False


def emit_start(run_id: str) -> bool:
    """Emit a START event for the retraining run."""

    return _emit("START", run_id)


def emit_complete(run_id: str) -> bool:
    """Emit a COMPLETE event for the retraining run."""

    return _emit("COMPLETE", run_id)


def emit_fail(run_id: str) -> bool:
    """Emit a FAIL event for the retraining run."""

    return _emit("FAIL", run_id)
