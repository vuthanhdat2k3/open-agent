from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_org_id, get_db, require_permission
from app.schemas.provider import (
    ProviderCreate,
    ProviderOut,
    ProviderTestResult,
    ProviderUpdate,
)
from app.services.provider_service import ProviderService

router = APIRouter(
    prefix="/api/providers",
    tags=["providers"],
)


@router.get("", response_model=list[ProviderOut], dependencies=[Depends(require_permission("providers:read"))])
async def list_providers(
    org_id: str = Depends(get_current_org_id), db: AsyncSession = Depends(get_db)
):
    return await ProviderService(db).list(org_id)


@router.post("", response_model=ProviderOut, status_code=201, dependencies=[Depends(require_permission("providers:manage"))])
async def create_provider(
    body: ProviderCreate,
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await ProviderService(db).create(org_id, body.model_dump())
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/{id}", response_model=ProviderOut, dependencies=[Depends(require_permission("providers:read"))])
async def get_provider(
    id: str, org_id: str = Depends(get_current_org_id), db: AsyncSession = Depends(get_db)
):
    p = await ProviderService(db).get(org_id, id)
    if p is None:
        raise HTTPException(404, "provider not found")
    return p


@router.put("/{id}", response_model=ProviderOut, dependencies=[Depends(require_permission("providers:manage"))])
async def update_provider(
    id: str,
    body: ProviderUpdate,
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await ProviderService(db).update(org_id, id, body.model_dump(exclude_unset=True))
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.delete("/{id}", dependencies=[Depends(require_permission("providers:manage"))])
async def delete_provider(
    id: str, org_id: str = Depends(get_current_org_id), db: AsyncSession = Depends(get_db)
):
    try:
        if not await ProviderService(db).delete(org_id, id):
            raise HTTPException(404, "provider not found")
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


@router.post("/{id}/test", response_model=ProviderTestResult, dependencies=[Depends(require_permission("providers:manage"))])
async def test_provider(
    id: str, org_id: str = Depends(get_current_org_id), db: AsyncSession = Depends(get_db)
):
    return await ProviderService(db).test_connection(org_id, id)
