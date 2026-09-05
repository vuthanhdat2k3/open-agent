"""User deactivation: soft-delete + full integration disconnect."""

import httpx
import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.customer_intelligence import (
    CalendarConnection,
    CiSchedule,
    DriveConnection,
    EmailConnection,
)
from app.models.membership import Membership
from app.models.role import Role
from app.models.user import User

PASSWORD = "Secret123!"


@pytest.fixture
async def async_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield session_factory
    await engine.dispose()


@pytest.fixture
async def client(async_session_factory):
    async def _override():
        async with async_session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def _register(api_client: httpx.AsyncClient, email: str, org_name: str | None = None) -> tuple[str, str | None]:
    body: dict[str, str] = {"email": email, "password": PASSWORD}
    if org_name:
        body["org_name"] = org_name
    resp = await api_client.post("/api/auth/register", json=body)
    assert resp.status_code == 201, resp.text
    token = resp.json()["access_token"]
    org_id = None
    if org_name:
        me = await api_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        org_id = me.json()["memberships"][0]["org_id"]
    return token, org_id


async def _seed_platform_admin(factory, org_id: str, email: str) -> None:
    """Replace this user's role-row(s) in org_id with a single platform_admin
    row. A blanket UPDATE would try to set every one of the user's role-rows
    (a self-registered founder has two: org_admin + operator) to
    platform_admin, colliding on the (org_id, user_id, role) unique
    constraint - delete first, then insert the one row we actually want."""
    async with factory() as session:
        user = (
            await session.execute(select(User).where(User.email == email))
        ).scalar_one()
        await session.execute(
            delete(Membership).where(Membership.org_id == org_id, Membership.user_id == user.id)
        )
        session.add(Membership(org_id=org_id, user_id=user.id, role=Role.platform_admin))
        await session.commit()


async def _seed_connections(factory, org_id: str, user_email: str) -> str:
    async with factory() as session:
        user = (
            await session.execute(select(User).where(User.email == user_email))
        ).scalar_one()
        email_conn = EmailConnection(
            org_id=org_id, provider="gmail", account_email="owned@gmail.com",
            status="connected", credentials_enc="enc-creds", created_by_user_id=user.id,
        )
        session.add(email_conn)
        await session.flush()
        session.add(CiSchedule(org_id=org_id, connection_id=email_conn.id, run_time="06:00", enabled=True))
        session.add(
            CalendarConnection(
                org_id=org_id, provider="google", account_email="owned-cal@gmail.com", status="connected",
                credentials_enc="enc-creds", created_by_user_id=user.id,
            )
        )
        session.add(
            DriveConnection(
                org_id=org_id, provider="google", account_email="owned-drive@gmail.com", status="connected",
                credentials_enc="enc-creds", created_by_user_id=user.id,
            )
        )
        await session.commit()
        return email_conn.id


async def _member_id(api_client: httpx.AsyncClient, token: str, org_id: str, email: str) -> str:
    resp = await api_client.get(f"/api/orgs/{org_id}/members", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    for member in resp.json():
        if member["email"] == email:
            return member["user_id"]
    raise AssertionError(f"member {email} not found")


async def test_deactivate_soft_deletes_and_disconnects_integrations(client, async_session_factory):
    admin_token, org_id = await _register(client, "deactivator@example.com", "Deactivate Org")
    await _seed_platform_admin(async_session_factory, org_id, "deactivator@example.com")
    target_token, _ = await _register(client, "leaver@example.com")
    target_id = (
        await client.get("/api/auth/me", headers={"Authorization": f"Bearer {target_token}"})
    ).json()["id"]
    email_conn_id = await _seed_connections(async_session_factory, org_id, "leaver@example.com")

    resp = await client.post(
        f"/api/users/{target_id}/deactivate",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200, resp.text

    async with async_session_factory() as session:
        user = (await session.execute(select(User).where(User.id == target_id))).scalar_one()
        assert user.is_active is False
        assert user.lifecycle_status == "inactive"
        memberships = (
            await session.execute(select(Membership).where(Membership.user_id == target_id))
        ).scalars().all()
        assert memberships and all(m.lifecycle_status == "inactive" for m in memberships)
        conns = (
            await session.execute(
                select(EmailConnection).where(EmailConnection.created_by_user_id == target_id)
            )
        ).scalars().all()
        assert conns and all(
            c.status == "disconnected" and c.credentials_enc is None for c in conns
        )
        schedules = (
            await session.execute(
                select(CiSchedule).where(CiSchedule.connection_id == email_conn_id)
            )
        ).scalars().all()
        assert schedules and all(s.enabled is False for s in schedules)


async def test_deactivated_user_cannot_log_in(client, async_session_factory):
    admin_token, org_id = await _register(client, "deactivator2@example.com", "Deactivate Org 2")
    await _seed_platform_admin(async_session_factory, org_id, "deactivator2@example.com")
    target_token, _ = await _register(client, "gone@example.com")
    target_id = (
        await client.get("/api/auth/me", headers={"Authorization": f"Bearer {target_token}"})
    ).json()["id"]

    resp = await client.post(
        f"/api/users/{target_id}/deactivate",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200

    login = await client.post(
        "/api/auth/login", json={"email": "gone@example.com", "password": PASSWORD}
    )
    assert login.status_code in (401, 403)


async def test_deactivate_unknown_user_returns_404(client, async_session_factory):
    admin_token, org_id = await _register(client, "deactivator3@example.com", "Deactivate Org 3")
    await _seed_platform_admin(async_session_factory, org_id, "deactivator3@example.com")

    resp = await client.post(
        "/api/users/00000000-0000-0000-0000-000000000000/deactivate",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 404


async def test_non_platform_admin_cannot_deactivate(client):
    token, _ = await _register(client, "plain-admin@example.com", "Plain Org")
    target_token, _ = await _register(client, "victim@example.com")
    target_id = (
        await client.get("/api/auth/me", headers={"Authorization": f"Bearer {target_token}"})
    ).json()["id"]

    resp = await client.post(
        f"/api/users/{target_id}/deactivate",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
