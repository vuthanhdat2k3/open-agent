"""Bootstrap the database, seed defaults, and run the REST API via uvicorn."""

from __future__ import annotations

import asyncio

import uvicorn

from rag_service.db.base import init_db
from rag_service.main import create_rest_app
from rag_service.scripts.seed import seed_default_collection


def run() -> None:
    asyncio.run(init_db())
    asyncio.run(seed_default_collection())
    app = create_rest_app()
    uvicorn.run(app, host="0.0.0.0", port=8100, reload=False)


if __name__ == "__main__":
    run()
