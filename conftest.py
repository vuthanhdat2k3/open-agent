"""Root test bootstrap for the multi-package repository.

Root pytest runs backend and rag-service together. Keep it offline from
production: use disposable SQLite settings, a dedicated local Redis DB for
quota tests, and run backend-relative Alembic commands from ``backend``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
RAG_SERVICE = ROOT / "rag-service"

for path in (str(BACKEND), str(RAG_SERVICE)):
    if path not in sys.path:
        sys.path.insert(0, path)

os.environ["OPENAGENT_DB_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["OPENAGENT_REDIS_URL"] = "redis://127.0.0.1:6379/15"
os.environ["OPENAGENT_WORKFLOW_EXECUTION_MODE"] = "inline"
os.environ["OPENAGENT_OTEL_ENABLED"] = "false"
os.environ["RAG_ENV"] = "test"
os.environ["RAG_VECTOR_STORE"] = "memory"
os.environ["RAG_BM25_BACKEND"] = "memory"
os.environ["RAG_EMBEDDER"] = "simple"
os.environ["OPENAI_API_KEY"] = ""


def pytest_configure(config) -> None:
    os.environ["OPENAGENT_DB_URL"] = "sqlite+aiosqlite:///:memory:"
    os.environ["OPENAGENT_REDIS_URL"] = "redis://127.0.0.1:6379/15"
    from app.config import get_settings

    get_settings.cache_clear()


# A few backend migration tests construct Config("alembic.ini") relative to
# their package root. Collection resolves test paths first; the session-start
# hook below handles those relative migration commands afterward.


def pytest_sessionstart(session) -> None:
    os.chdir(BACKEND)
