"""Structured logging for PR-07 observability (B4 contract).

Application log entries are emitted as structured JSON with at least these
fields::

    {"timestamp": ISO8601, "level": str, "event": str, "component": str,
     "artifact": str | null, "status": str | null}

An optional ``error`` key may carry a short message only (never a traceback,
never artifact payloads, never absolute paths or secrets).

Uses the standard library ``logging`` module with a JSON-passthrough formatter
on a dedicated, non-propagating logger so it stays independent of any other
logging configuration in the repo.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

_LOGGER_NAME = "invforge.observability"

_LEVELS: dict[str, int] = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
}


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_handler() -> logging.Logger:
    logger = logging.getLogger(_LOGGER_NAME)
    if not getattr(logger, "_invforge_configured", False):
        handler = logging.StreamHandler(stream=sys.stdout)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
        logger._invforge_configured = True  # type: ignore[attr-defined]
    return logger


class ObservabilityLogger:
    """Emit safe, structured JSON log lines for a single component."""

    def __init__(self, component: str) -> None:
        self.component = component
        self._logger = _ensure_handler()

    def log(
        self,
        event: str,
        *,
        level: str = "info",
        artifact: str | None = None,
        status: str | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        """Build, emit, and return a structured log record.

        ``error`` must be a short message only; tracebacks and payloads are
        never logged.
        """

        record: dict[str, Any] = {
            "timestamp": _iso_now(),
            "level": level,
            "event": event,
            "component": self.component,
            "artifact": artifact,
            "status": status,
        }
        if error is not None:
            record["error"] = error
        self._logger.log(
            _LEVELS.get(level, logging.INFO),
            json.dumps(record, sort_keys=True),
        )
        return record


def get_logger(component: str) -> ObservabilityLogger:
    """Return an :class:`ObservabilityLogger` bound to ``component``."""

    return ObservabilityLogger(component)
