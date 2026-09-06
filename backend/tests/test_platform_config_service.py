"""PlatformConfigService: DB-backed overrides for the allow-listed
platform_admin-editable Settings fields (Group 3 only — never core
auth/DB/session secrets, see platform_config_schema.py's docstring).
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.services.platform_config_service import PlatformConfigService


@pytest.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.fixture(autouse=True)
def _clean_environ():
    # Every test in this module touches os.environ via the service; make
    # sure a value set by one test can never leak into the next.
    keys = ["OPENAGENT_TINYFISH_API_KEY", "OPENAGENT_LANGFUSE_ENABLED", "OPENAGENT_WORKFLOW_MAX_CONCURRENCY"]
    saved = {k: os.environ.get(k) for k in keys}
    yield
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


async def test_rejects_a_key_outside_the_allow_list(session_factory):
    async with session_factory() as db:
        service = PlatformConfigService(db)
        with pytest.raises(ValueError, match="not an editable platform setting"):
            await service.set_value("jwt_secret_key", "anything", user_id=None)


async def test_set_value_persists_and_applies_to_environ(session_factory):
    async with session_factory() as db:
        service = PlatformConfigService(db)
        result = await service.set_value("tinyfish_api_key", "sk-test-123", user_id="user-1")
        assert result["is_set"] is True
        assert result["masked_value"] != "sk-test-123"  # never echoes the raw secret back
        assert os.environ["OPENAGENT_TINYFISH_API_KEY"] == "sk-test-123"


async def test_boolean_field_coerces_from_various_truthy_inputs(session_factory):
    async with session_factory() as db:
        service = PlatformConfigService(db)
        await service.set_value("langfuse_enabled", True, user_id=None)
        assert os.environ["OPENAGENT_LANGFUSE_ENABLED"] == "true"
        await service.set_value("langfuse_enabled", "false", user_id=None)
        assert os.environ["OPENAGENT_LANGFUSE_ENABLED"] == "false"


async def test_options_field_rejects_a_value_outside_its_choices(session_factory):
    async with session_factory() as db:
        service = PlatformConfigService(db)
        with pytest.raises(ValueError, match="not one of"):
            await service.set_value("workflow_execution_mode", "sideways", user_id=None)


async def test_number_field_rejects_a_non_numeric_value(session_factory):
    async with session_factory() as db:
        service = PlatformConfigService(db)
        with pytest.raises(ValueError):
            await service.set_value("workflow_max_concurrency", "not-a-number", user_id=None)


async def test_reset_value_removes_override_and_environ_entry(session_factory):
    async with session_factory() as db:
        service = PlatformConfigService(db)
        await service.set_value("tinyfish_api_key", "sk-test-123", user_id=None)
        assert "OPENAGENT_TINYFISH_API_KEY" in os.environ

        await service.reset_value("tinyfish_api_key")
        assert "OPENAGENT_TINYFISH_API_KEY" not in os.environ

        entries = await service.list_effective()
        entry = next(e for e in entries if e["key"] == "tinyfish_api_key")
        assert entry["is_overridden"] is False


async def test_apply_overrides_to_environ_loads_every_saved_row(session_factory):
    """Simulates a fresh process start: a row saved by an earlier session
    (e.g. the api container) must be picked up by a brand-new session (e.g.
    the worker container's own startup) against the same database."""
    async with session_factory() as write_db:
        await PlatformConfigService(write_db).set_value("tinyfish_api_key", "sk-startup-value", user_id=None)

    os.environ.pop("OPENAGENT_TINYFISH_API_KEY", None)  # simulate a fresh process

    async with session_factory() as read_db:
        applied = await PlatformConfigService(read_db).apply_overrides_to_environ()

    assert applied >= 1
    assert os.environ["OPENAGENT_TINYFISH_API_KEY"] == "sk-startup-value"


async def test_list_effective_never_returns_raw_secret_value(session_factory):
    async with session_factory() as db:
        service = PlatformConfigService(db)
        await service.set_value("tinyfish_api_key", "sk-super-secret-value", user_id=None)
        entries = await service.list_effective()
        entry = next(e for e in entries if e["key"] == "tinyfish_api_key")
        assert "value" not in entry
        assert "sk-super-secret-value" not in str(entry)
