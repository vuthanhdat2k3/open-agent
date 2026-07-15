"""SSE / HTTP MCP transport app factory."""

from __future__ import annotations

from typing import Any

from rag_service.core.logging import logger


def create_sse_app(mcp_server: Any) -> Any:
    """Return an ASGI app serving the MCP server over SSE / HTTP.

    Prefers the FastMCP provided app factory; otherwise builds a Starlette app
    manually using :class:`mcp.server.sse.SseServerTransport`.
    """
    # FastMCP provides a ready-made Starlette app.
    sse_app = getattr(mcp_server, "sse_app", None)
    streamable_app = getattr(mcp_server, "streamable_http_app", None)
    if callable(sse_app):
        try:
            return sse_app()
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("mcp_sse_app_failed", error=str(exc))

    if callable(streamable_app):
        try:
            return streamable_app()
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("mcp_streamable_app_failed", error=str(exc))

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

    return Starlette(
        routes=[
            Route("/sse", endpoint=handle_sse),
            Mount("/messages", app=sse.handle_post_message),
        ]
    )
