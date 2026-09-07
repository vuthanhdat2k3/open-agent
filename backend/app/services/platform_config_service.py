from __future__ import annotations

import os
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.platform_config_schema import PLATFORM_CONFIG_BY_KEY, ConfigField
from app.db.base import utc_now
from app.models.platform_config import PlatformConfig

_ENV_PREFIX = "OPENAGENT_"


def _env_name(key: str) -> str:
    return f"{_ENV_PREFIX}{key.upper()}"


def _mask(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "•" * len(value)
    return f"{value[:4]}…{value[-4:]}"


class PlatformConfigService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def apply_overrides_to_environ(self) -> int:
        """Layer every stored override onto this process's environment so the
        next (uncached, per-call) `Settings()` construction picks it up.

        Called once at process startup, and again on a short cron tick in
        the worker so a change saved through the API (which only updates
        the api process's own environ immediately) reaches the separate
        worker process within roughly a minute — no pub/sub needed for an
        instance-wide config knob that isn't latency-sensitive.
        """
        res = await self.db.execute(select(PlatformConfig))
        rows = res.scalars().all()
        applied = 0
        for row in rows:
            if row.key not in PLATFORM_CONFIG_BY_KEY:
                continue  # stale row for a field removed from the allow-list
            os.environ[_env_name(row.key)] = row.value
            applied += 1
        if applied:
            get_settings.cache_clear()  # get_settings() is @lru_cache'd; force a fresh read
        return applied

    async def list_effective(self) -> list[dict[str, Any]]:
        res = await self.db.execute(select(PlatformConfig))
        overridden_keys = {row.key for row in res.scalars().all()}
        settings = get_settings()
        out: list[dict[str, Any]] = []
        for field in PLATFORM_CONFIG_BY_KEY.values():
            raw = getattr(settings, field.key, "")
            entry: dict[str, Any] = {
                "key": field.key,
                "label": field.label,
                "group": field.group,
                "type": field.type,
                "description": field.description,
                "options": list(field.options) if field.options else None,
                "is_overridden": field.key in overridden_keys,
            }
            if field.type == "secret":
                str_value = str(raw or "")
                entry["is_set"] = bool(str_value)
                entry["masked_value"] = _mask(str_value)
            else:
                entry["value"] = raw
            out.append(entry)
        return out

    async def set_value(self, key: str, raw_value: Any, user_id: str | None) -> dict[str, Any]:
        field = PLATFORM_CONFIG_BY_KEY.get(key)
        if field is None:
            raise ValueError(f"'{key}' is not an editable platform setting")
        str_value = self._coerce_to_string(field, raw_value)

        row = await self.db.get(PlatformConfig, key)
        if row is None:
            row = PlatformConfig(key=key, value=str_value, updated_by_user_id=user_id)
            self.db.add(row)
        else:
            row.value = str_value
            row.updated_by_user_id = user_id
            row.updated_at = utc_now()
        await self.db.commit()

        os.environ[_env_name(key)] = str_value
        get_settings.cache_clear()  # get_settings() is @lru_cache'd; force a fresh read
        return await self._one(key)

    async def reset_value(self, key: str) -> None:
        if key not in PLATFORM_CONFIG_BY_KEY:
            raise ValueError(f"'{key}' is not an editable platform setting")
        row = await self.db.get(PlatformConfig, key)
        if row is not None:
            await self.db.delete(row)
            await self.db.commit()
        os.environ.pop(_env_name(key), None)
        get_settings.cache_clear()  # get_settings() is @lru_cache'd; force a fresh read

    async def _one(self, key: str) -> dict[str, Any]:
        for entry in await self.list_effective():
            if entry["key"] == key:
                return entry
        raise ValueError(f"'{key}' is not an editable platform setting")

    @staticmethod
    def _coerce_to_string(field: ConfigField, raw_value: Any) -> str:
        if field.type == "boolean":
            if isinstance(raw_value, str):
                return "true" if raw_value.strip().lower() in {"1", "true", "yes", "on"} else "false"
            return "true" if bool(raw_value) else "false"
        if field.type == "options" and field.options and str(raw_value) not in field.options:
            raise ValueError(f"'{raw_value}' is not one of {field.options} for '{field.key}'")
        if field.type == "number":
            float(raw_value)  # raises ValueError for a non-numeric input
        return str(raw_value)
