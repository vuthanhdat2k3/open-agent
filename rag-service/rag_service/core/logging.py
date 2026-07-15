"""Structured logging configuration.

Uses :mod:`structlog` when available, otherwise falls back to the standard
library so the service has no hard dependency on structlog.
"""

from __future__ import annotations

import logging
import sys

from rag_service.config import settings


def configure_logging() -> None:
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logging.basicConfig(
        format="%(message)s",
        level=level,
        stream=sys.stdout,
        force=True,
    )
    try:  # pragma: no cover - optional dependency
        import structlog

        structlog.configure(
            wrapper_class=structlog.make_filtering_bound_logger(level),
            processors=[
                structlog.contextvars.merge_contextvars,
                structlog.processors.add_log_level,
                structlog.processors.TimeStamper(fmt="iso"),
                (
                    structlog.processors.JSONRenderer()
                    if settings.log_format == "json"
                    else structlog.dev.ConsoleRenderer()
                ),
            ],
        )
    except Exception:  # pragma: no cover - structlog not installed
        pass


def get_logger(name: str):
    try:  # pragma: no cover - optional dependency
        import structlog

        return structlog.get_logger(name)
    except Exception:  # pragma: no cover
        return logging.getLogger(name)


# Configure once on import so any module importing this gets a ready logger.
configure_logging()
logger = get_logger("rag_service")
