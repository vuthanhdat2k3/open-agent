from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db, require_permission
from app.models.user import User
from app.services.platform_config_service import PlatformConfigService

router = APIRouter(prefix="/api/platform/config", tags=["platform-config"])


class SetConfigValue(BaseModel):
    value: Any


@router.get("", dependencies=[Depends(require_permission("platform:config:read"))])
async def list_platform_config(db: AsyncSession = Depends(get_db)):
    return await PlatformConfigService(db).list_effective()


@router.put("/{key}", dependencies=[Depends(require_permission("platform:config:manage"))])
async def set_platform_config(
    key: str,
    body: SetConfigValue,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await PlatformConfigService(db).set_value(key, body.value, current_user.id)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.delete("/{key}", dependencies=[Depends(require_permission("platform:config:manage"))])
async def reset_platform_config(key: str, db: AsyncSession = Depends(get_db)):
    try:
        await PlatformConfigService(db).reset_value(key)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"ok": True}
