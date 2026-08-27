"""Tests for Workflow Marketplace and Single-Ownership Model."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import jwt
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.role import Role
from app.models.user import User
from app.models.workflow import Workflow


@pytest.fixture
async def async_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield session_factory
    await engine.dispose()


@pytest.fixture
def client(async_session_factory):
    async def _override_get_db():
        async with async_session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db
    c = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    yield c
    app.dependency_overrides.clear()


@pytest.fixture
def token_factory():
    def _make(user_id: str, org_id: str, role: str = "user") -> str:
        payload = {
            "sub": user_id,
            "org_id": org_id,
            "role": role,
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }
        return jwt.encode(payload, get_settings().jwt_secret_key, algorithm="HS256")

    return _make


@pytest.mark.asyncio
async def test_workflow_single_ownership_and_marketplace(async_session_factory, client, token_factory) -> None:
    async with async_session_factory() as session:
        org = Organization(name="Market Org", slug="market-org")
        session.add(org)
        await session.flush()

        operator = User(email="operator@org.com", hashed_password="pw")
        member = User(email="member@org.com", hashed_password="pw")
        session.add_all([operator, member])
        await session.flush()

        # Operator membership
        session.add(Membership(org_id=org.id, user_id=operator.id, role=Role.operator))
        # User membership
        session.add(Membership(org_id=org.id, user_id=member.id, role=Role.user))
        await session.commit()

        op_token = token_factory(user_id=operator.id, org_id=org.id, role="operator")
        member_token = token_factory(user_id=member.id, org_id=org.id, role="user")

    # 1. Operator creates a workflow
    res = await client.post(
        "/api/workflows",
        headers={"Authorization": f"Bearer {op_token}", "X-Organization-Id": org.id},
        json={
            "name": "Operator Lead Scanner",
            "description": "Daily automated scanner",
            "graph": {
                "nodes": [
                    {"id": "in", "kind": "input", "parameters": {"input_field": "Run input"}},
                    {"id": "agent", "kind": "agent", "parameters": {"system_prompt": "Scan leads", "model_id": "m1"}},
                    {"id": "out", "kind": "output", "parameters": {"include": "all_inputs"}},
                ],
                "edges": [
                    {"from_": "in", "to": "agent"},
                    {"from_": "agent", "to": "out"},
                ],
            },
        },
    )
    assert res.status_code == 201, res.text
    op_wf_id = res.json()["id"]

    # 2. Member lists workflows -> cannot see operator's workflow
    res = await client.get(
        "/api/workflows",
        headers={"Authorization": f"Bearer {member_token}", "X-Organization-Id": org.id},
    )
    assert res.status_code == 200
    member_wfs = res.json()
    assert not any(w["id"] == op_wf_id for w in member_wfs)

    # 3. Operator publishes workflow to Marketplace
    res = await client.post(
        "/api/workflow-catalog/publish",
        headers={"Authorization": f"Bearer {op_token}", "X-Organization-Id": org.id},
        json={
            "workflow_id": op_wf_id,
            "category": "customer_intelligence",
            "description": "Published template for lead scanning",
            "outcome": "Find new leads daily",
            "icon": "zap",
        },
    )
    assert res.status_code == 200, res.text
    catalog_item = res.json()
    template_key = catalog_item["key"]

    # 4. Member browses Marketplace and installs the template
    res = await client.get(
        "/api/workflow-catalog/templates",
        headers={"Authorization": f"Bearer {member_token}", "X-Organization-Id": org.id},
    )
    assert res.status_code == 200
    templates = res.json()["data"]
    assert any(t["key"] == template_key for t in templates)

    res = await client.post(
        "/api/workflow-catalog/installations",
        headers={"Authorization": f"Bearer {member_token}", "X-Organization-Id": org.id},
        json={
            "template_key": template_key,
            "name": "My Personal Lead Scanner",
            "timezone": "Asia/Ho_Chi_Minh",
            "schedule": {"kind": "daily", "time": "08:00"},
            "settings": {},
        },
    )
    assert res.status_code == 201, res.text
    installation = res.json()
    member_wf_id = installation["workflow_id"]
    assert member_wf_id != op_wf_id

    # 5. Member edits and updates their installed workflow -> SUCCESS 200 OK (no 403!)
    res = await client.put(
        f"/api/workflows/{member_wf_id}",
        headers={"Authorization": f"Bearer {member_token}", "X-Organization-Id": org.id},
        json={
            "name": "My Personal Lead Scanner (Customized)",
            "graph": {
                "nodes": [
                    {"id": "in", "kind": "input", "parameters": {"input_field": "Run input"}},
                    {"id": "agent", "kind": "agent", "parameters": {"system_prompt": "Customized prompt for member", "model_id": "m1"}},
                    {"id": "out", "kind": "output", "parameters": {"include": "all_inputs"}},
                ],
                "edges": [
                    {"from_": "in", "to": "agent"},
                    {"from_": "agent", "to": "out"},
                ],
            },
        },
    )
    assert res.status_code == 200, res.text
    updated_wf = res.json()
    assert updated_wf["name"] == "My Personal Lead Scanner (Customized)"

    # 6. Member lists workflows -> now sees their own installed workflow
    res = await client.get(
        "/api/workflows",
        headers={"Authorization": f"Bearer {member_token}", "X-Organization-Id": org.id},
    )
    assert res.status_code == 200
    my_wfs = res.json()
    assert any(w["id"] == member_wf_id for w in my_wfs)
    assert not any(w["id"] == op_wf_id for w in my_wfs)
