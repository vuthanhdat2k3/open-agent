"""SSE / HTTP MCP transport app factory."""

from __future__ import annotations

from typing import Any

from rag_service.config import settings
from rag_service.core.logging import logger


class _ApiKeyMiddleware:
    """Require ``X-API-Key`` on every HTTP request, mirroring the REST admin
    API's ``api_key_auth`` policy (see ``api/v1/router.py``). The MCP tools
    exposed here (rag_ingest_url, rag_delete_document, ...) are just as
    sensitive as the REST endpoints and must not be reachable unauthenticated
    once the service is off a trusted-only network.
    """

    def __init__(self, app: Any) -> None:
        self._app = app

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        provided = headers.get(b"x-api-key", b"").decode("utf-8", errors="ignore")

        if settings.api_key:
            authorized = provided == settings.api_key
        else:
            authorized = settings.env != "production"

        if not authorized:
            from starlette.responses import JSONResponse

            resp = JSONResponse(
                {"error": "Invalid or missing X-API-Key"},
                status_code=401 if settings.api_key else 503,
            )
            await resp(scope, receive, send)
            return

        await self._app(scope, receive, send)


def create_sse_app(mcp_server: Any) -> Any:
    """Return an ASGI app serving the MCP server over SSE / HTTP, gated by
    the same X-API-Key policy as the REST admin API.

    Prefers the FastMCP provided app factory; otherwise builds a Starlette app
    manually using :class:`mcp.server.sse.SseServerTransport`.
    """
    app: Any = None

    # FastMCP provides a ready-made Starlette app.
    # Note: FastMCP.sse_app() takes no `transport_security` argument — that
    # setting is baked in at FastMCP(..., transport_security=...) construction
    # time (see mcp_server/server.py) and read from self.settings internally.
    sse_app = getattr(mcp_server, "sse_app", None)
    streamable_app = getattr(mcp_server, "streamable_http_app", None)
    if callable(sse_app):
        try:
            app = sse_app()
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("mcp_sse_app_failed", error=str(exc))

    if app is None and callable(streamable_app):
        try:
            app = streamable_app()
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("mcp_streamable_app_failed", error=str(exc))

    if app is None:
        # Manual fallback for the low-level Server object.
        from mcp.server.sse import SseServerTransport
        from starlette.applications import Starlette
        from starlette.routing import Mount, Route

        sse = SseServerTransport("/messages")

        async def handle_sse(request: Any) -> None:
            async with sse.connect_sse(
                request.scope, request.receive, request._send
            ) as streams:
                await mcp_server.run(
                    streams[0],
                    streams[1],
                    mcp_server.create_initialization_options(),
                )

        app = Starlette(
            routes=[
                Route("/sse", endpoint=handle_sse),
                Mount("/messages", app=sse.handle_post_message),
            ]
        )

    return _ApiKeyMiddleware(app)
