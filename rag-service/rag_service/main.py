"""Application factory for the RAG REST admin API.

Production deployments import :func:`create_rest_app`; the MCP server and CLI
entrypoints reuse the same components. On startup we create the schema (if
needed) and make sure the ``default`` collection exists so ingestion into
``"default"`` works out of the box.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from rag_service.api.v1.router import (
    api_router,
    rag_error_handler,
    unhandled_error_handler,
)
from rag_service.config import settings
from rag_service.core.logging import logger
from rag_service.exceptions import RAGError
from rag_service import __version__


@asynccontextmanager
async def lifespan(app: FastAPI):
    from rag_service.db.base import get_sessionmaker, init_db
    from rag_service.dependencies import get_components
    from rag_service.services.collection_service import CollectionService

    await init_db()
    maker = get_sessionmaker()
    async with maker() as session:
        svc = CollectionService(session, get_components())
        await svc.ensure_default()
    logger.info("rag_rest_startup_complete")
    yield


def create_rest_app() -> FastAPI:
    """Build the FastAPI app exposing the v1 admin API under ``/api/v1``."""
    settings.ensure_dirs()

    app = FastAPI(
        title="OpenAgent RAG Service",
        version=__import__("rag_service").__version__,
        description="REST admin API for the RAG microservice (hybrid BM25 + semantic retrieval).",
        lifespan=lifespan,
    )

    app.include_router(api_router, prefix="/api/v1")

    app.add_exception_handler(RAGError, rag_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)

    @app.get("/", include_in_schema=False)
    async def root() -> dict:
        return {"service": "rag", "docs": "/docs", "health": "/api/v1/health"}

    return app


    # Allow `python -m rag_service.main` / uvicorn rag_service.main:app.
app = create_rest_app()


def create_mcp_sse_app():
    """Build the ASGI app serving the MCP server over SSE."""
    from rag_service.mcp_server.server import create_mcp_server
    from rag_service.mcp_server.transport.sse import create_sse_app

    return create_sse_app(create_mcp_server())


def _serve(app, host: str, port: int) -> None:  # pragma: no cover - runtime
    import uvicorn

    uvicorn.run(app, host=host, port=port)


def main() -> None:  # pragma: no cover - runtime entrypoint
    """Run the service based on ``settings.mcp_transport``.

    * ``stdio`` — block running the MCP server on stdio.
    * ``sse``   — run REST + MCP-SSE on separate ports (threads).
    * ``both``  — same as ``sse`` (the MCP client launches stdio on demand).
    """
    transport = (settings.mcp_transport or "both").lower()

    if transport == "stdio":
        from rag_service.mcp_server.transport.stdio import main as stdio_main

        stdio_main()
        return

    rest_app = create_rest_app()
    mcp_app = create_mcp_sse_app()

    import threading

    t_rest = threading.Thread(
        target=_serve, args=(rest_app, settings.rest_host, settings.rest_port), daemon=True
    )
    t_mcp = threading.Thread(
        target=_serve, args=(mcp_app, settings.mcp_host, settings.mcp_port), daemon=True
    )
    t_rest.start()
    t_mcp.start()

    print("=" * 60)
    print(f"RAG Service v{__version__}  (transport={transport})")
    print(f"  REST admin API : http://{settings.rest_host}:{settings.rest_port}")
    print(f"  MCP SSE server : http://{settings.mcp_host}:{settings.mcp_port}/sse")
    if transport == "both":
        print("  (MCP stdio is launched on demand by the client)")
    print("=" * 60)

    try:
        t_rest.join()
        t_mcp.join()
    except KeyboardInterrupt:  # pragma: no cover
        pass


if __name__ == "__main__":
    main()
