from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable

import structlog
from fastapi import Request, Response
from structlog.contextvars import bind_contextvars, clear_contextvars

from app.config import get_settings


def configure_logging() -> None:
    renderer = (
        structlog.processors.JSONRenderer()
        if get_settings().log_format == "json"
        else structlog.dev.ConsoleRenderer()
    )
    logging.basicConfig(level=get_settings().log_level)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        cache_logger_on_first_use=True,
    )


async def request_context_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    clear_contextvars()
    request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
    bind_contextvars(request_id=request_id)
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-Id"] = request_id
    clear_contextvars()
    return response

