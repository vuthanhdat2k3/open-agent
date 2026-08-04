from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _skip_lifespan_db_init(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stop TestClient lifespan from migrating the real database.

    ``app.main.lifespan`` calls ``init_db()`` against the global engine, which
    in the local .env points at a remote Postgres. Every TestClient runs its
    own event loop; asyncpg connections pooled by the global engine are bound
    to whichever loop created them, so the next TestClient reuses a stale
    connection and crashes at startup with "Event loop is closed". Tests
    exercise DB logic through their own in-memory engines (get_db overrides),
    so the production migration is unnecessary and harmful here.
    """
    import app.main as main

    async def _noop_init_db() -> None:
        return None

    monkeypatch.setattr(main, "init_db", _noop_init_db)
    yield
