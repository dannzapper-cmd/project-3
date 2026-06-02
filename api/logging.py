"""Structured logging setup for InvForge services."""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

SERVICE_NAME = "invforge-api"


def _add_service(
    _logger: logging.Logger,
    _method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    event_dict.setdefault("service", SERVICE_NAME)
    return event_dict


def configure_logging() -> None:
    """Configure JSON logs with timestamp, level, service, and message fields."""

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.INFO,
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            _add_service,
            structlog.processors.TimeStamper(fmt="iso", utc=True, key="timestamp"),
            structlog.processors.add_log_level,
            structlog.processors.EventRenamer("message"),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

