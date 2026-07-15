from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_api_key
from app.db.session import get_db
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
    dependencies=[Depends(verify_api_key)],
)


@router.get("", response_model=list[ProviderOut])
async def list_providers(db: AsyncSession = Depends(get_db)):
    return await ProviderService(db).list()


@router.post("", response_model=ProviderOut, status_code=201)
async def create_provider(
    body: ProviderCreate, db: AsyncSession = Depends(get_db)
):
    try:
        return await ProviderService(db).create(body.model_dump())
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/{id}", response_model=ProviderOut)
async def get_provider(id: str, db: AsyncSession = Depends(get_db)):
    p = await ProviderService(db).get(id)
    if p is None:
        raise HTTPException(404, "provider not found")
    return p


@router.put("/{id}", response_model=ProviderOut)
async def update_provider(
    id: str, body: ProviderUpdate, db: AsyncSession = Depends(get_db)
):
    try:
        return await ProviderService(db).update(
            id, body.model_dump(exclude_unset=True)
        )
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.delete("/{id}")
async def delete_provider(id: str, db: AsyncSession = Depends(get_db)):
    if not await ProviderService(db).delete(id):
        raise HTTPException(404, "provider not found")
    return {"ok": True}


@router.post("/{id}/test", response_model=ProviderTestResult)
async def test_provider(id: str, db: AsyncSession = Depends(get_db)):
    return await ProviderService(db).test_connection(id)
