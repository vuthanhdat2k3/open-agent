"""Workflow installation status guards (Fix #6).

Archived installations are soft-deleted: the catalog executor must not run
them and the pause/resume transitions must not silently flip an archived
row back to enabled/paused. The endpoint checks live behind RBAC so the
unit tests here just exercise the guard logic via a fake request context.
"""
from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.v1.routes.workflow_installations import (
    pause_installation,
    resume_installation,
    run_installation_now,
)


def _fake_installation(status: str) -> SimpleNamespace:
    return SimpleNamespace(
        id="inst-1",
        org_id="org-1",
        owner_user_id="user-1",
        template_key="t",
        template_version=1,
        workflow_id="wf-1",
        name="t",
        status=status,
        timezone="UTC",
        schedule={"kind": "daily", "time": "07:30"},
        settings={},
        next_run_at=datetime(2026, 1, 1, 0, 0, 0),
        created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 1),
    )


@pytest.mark.asyncio
async def test_run_installation_now_blocks_archived() -> None:
    """A user with `workflows:run` still must not be able to trigger an
    archived installation — it would still hit the worker, cost tokens,
    and pollute the activity log."""
    fake_db = MagicMock()
    fake_db.scalar = AsyncMock(return_value=_fake_installation("archived"))

    with pytest.raises(Exception) as exc_info:
        await run_installation_now(
            installation_id="inst-1",
            org_id="org-1",
            current_user=SimpleNamespace(id="user-1"),
            db=fake_db,
        )
    assert "archived" in str(exc_info.value).lower()
    # The handler must short-circuit before queuing anything.
    assert not fake_db.add.called


@pytest.mark.asyncio
async def test_pause_installation_blocks_archived() -> None:
    fake_db = MagicMock()
    fake_db.scalar = AsyncMock(return_value=_fake_installation("archived"))

    with pytest.raises(Exception) as exc_info:
        await pause_installation(
            installation_id="inst-1",
            org_id="org-1",
            current_user=SimpleNamespace(id="user-1"),
            db=fake_db,
        )
    assert "archived" in str(exc_info.value).lower()
    assert not fake_db.commit.called


@pytest.mark.asyncio
async def test_resume_installation_blocks_archived() -> None:
    fake_db = MagicMock()
    fake_db.scalar = AsyncMock(return_value=_fake_installation("archived"))

    with pytest.raises(Exception) as exc_info:
        await resume_installation(
            installation_id="inst-1",
            org_id="org-1",
            current_user=SimpleNamespace(id="user-1"),
            db=fake_db,
        )
    assert "archived" in str(exc_info.value).lower()
    assert not fake_db.commit.called
