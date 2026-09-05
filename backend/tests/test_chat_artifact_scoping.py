from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app import models  # noqa: F401
from app.api.v1.routes.sessions import list_messages
from app.db.base import Base
from app.models.message import Message
from app.models.organization import Organization
from app.models.session import Session
from app.models.user import User
from app.models.workspace import WorkspaceArtifact


@pytest.mark.asyncio
async def test_list_messages_scopes_artifacts_per_turn() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as db:
        # Create Org, User, Session
        org = Organization(id="org-test-scoping", name="Test Org", slug="test-scoping")
        user = User(id="user-test-scoping", email="user@example.com", display_name="Test User")
        sess = Session(
            id="sess-test-scoping",
            org_id=org.id,
            agent_id="agent-1",
            created_by_user_id=user.id,
            title="Artifact Scoping Test",
        )
        db.add_all([org, user, sess])
        await db.commit()

        base_time = datetime(2026, 9, 5, 10, 0, 0, tzinfo=timezone.utc)

        # Turn 1: User message, then Assistant message at base_time + 10s
        m_u1 = Message(
            id="msg-u1",
            session_id=sess.id,
            org_id=org.id,
            role="user",
            content="Draw a house",
            position=0,
            created_at=base_time,
        )
        m_a1 = Message(
            id="msg-a1",
            session_id=sess.id,
            org_id=org.id,
            role="assistant",
            content="Here is the house",
            position=1,
            created_at=base_time + timedelta(seconds=10),
            meta={"artifacts": []},
        )
        # Artifact 1 created during Turn 1 at base_time + 5s
        art1 = WorkspaceArtifact(
            id="art-house-1",
            org_id=org.id,
            session_id=sess.id,
            path="3d-house.html",
            content_type="text/html",
            size=1024,
            source_tool="run_code",
            created_at=base_time + timedelta(seconds=5),
            updated_at=base_time + timedelta(seconds=5),
        )

        # Turn 2: User message at base_time + 20s, Assistant message at base_time + 30s
        m_u2 = Message(
            id="msg-u2",
            session_id=sess.id,
            org_id=org.id,
            role="user",
            content="Write factorial in python",
            position=2,
            created_at=base_time + timedelta(seconds=20),
        )
        # Simulate legacy buggy meta which had both art1 and art2
        m_a2 = Message(
            id="msg-a2",
            session_id=sess.id,
            org_id=org.id,
            role="assistant",
            content="Here is factorial.py",
            position=3,
            created_at=base_time + timedelta(seconds=30),
            meta={"artifacts": [{"id": "art-house-1"}, {"id": "art-py-2"}]},
        )
        # Artifact 2 created during Turn 2 at base_time + 25s
        art2 = WorkspaceArtifact(
            id="art-py-2",
            org_id=org.id,
            session_id=sess.id,
            path="factorial.py",
            content_type="text/x-python",
            size=256,
            source_tool="run_code",
            created_at=base_time + timedelta(seconds=25),
            updated_at=base_time + timedelta(seconds=25),
        )

        db.add_all([m_u1, m_a1, art1, m_u2, m_a2, art2])
        await db.commit()

        # Call list_messages
        res = await list_messages(session_id=sess.id, org_id=org.id, db=db)

        assert len(res) == 4
        # Turn 1 assistant message should only have art1
        a1_out = res[1]
        assert a1_out.role == "assistant"
        assert len(a1_out.meta.get("artifacts", [])) == 1
        assert a1_out.meta["artifacts"][0]["id"] == "art-house-1"
        assert a1_out.meta["artifacts"][0]["filename"] == "3d-house.html"

        # Turn 2 assistant message should only have art2 (art1 leaked from turn 1 must be filtered out!)
        a2_out = res[3]
        assert a2_out.role == "assistant"
        assert len(a2_out.meta.get("artifacts", [])) == 1
        assert a2_out.meta["artifacts"][0]["id"] == "art-py-2"
        assert a2_out.meta["artifacts"][0]["filename"] == "factorial.py"


@pytest.mark.asyncio
async def test_subagent_artifact_scoping_with_inherited_session() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as db:
        org = Organization(id="org-subagent-test", name="Test Org Subagent", slug="test-subagent")
        user = User(id="user-subagent-test", email="user@example.com", display_name="Subagent Test User")
        sess = Session(
            id="sess-subagent-test",
            org_id=org.id,
            agent_id="agent-1",
            created_by_user_id=user.id,
            title="Subagent Artifact Test",
        )
        db.add_all([org, user, sess])
        await db.commit()

        base_time = datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)

        m_u1 = Message(
            id="msg-u1",
            session_id=sess.id,
            org_id=org.id,
            role="user",
            content="Draw an airplane in html",
            position=0,
            created_at=base_time,
        )
        m_a1 = Message(
            id="msg-a1",
            session_id=sess.id,
            org_id=org.id,
            role="assistant",
            content="I created airplane.html",
            position=1,
            created_at=base_time + timedelta(seconds=15),
            meta=None,
        )
        # Artifact created by subagent with root_run_id and session_id
        art_airplane = WorkspaceArtifact(
            id="art-airplane-1",
            org_id=org.id,
            session_id=sess.id,
            root_run_id="run-airplane-1",
            path="airplane.html",
            content_type="text/html",
            size=2048,
            source_tool="preview_web_artifact",
            created_at=base_time + timedelta(seconds=10),
            updated_at=base_time + timedelta(seconds=10),
        )

        db.add_all([m_u1, m_a1, art_airplane])
        await db.commit()

        res = await list_messages(session_id=sess.id, org_id=org.id, db=db)
        assert len(res) == 2
        a1_out = res[1]
        assert a1_out.role == "assistant"
        artifacts = a1_out.meta.get("artifacts", [])
        assert len(artifacts) == 1
        assert artifacts[0]["id"] == "art-airplane-1"
        assert artifacts[0]["filename"] == "airplane.html"
        assert artifacts[0]["source_tool"] == "preview_web_artifact"
