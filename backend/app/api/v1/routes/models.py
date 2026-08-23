from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_org_id, get_db, require_permission
from app.schemas.model import ModelCreate, ModelOut, ModelTestResult, ModelUpdate
from app.services.model_service import ModelService

router = APIRouter(
    prefix="/api/models",
    tags=["models"],
)


@router.get("", response_model=list[ModelOut], dependencies=[Depends(require_permission("models:read"))])
async def list_models(
    with_inactive: bool = False,
    active: bool | None = None,
    provider: str | None = None,
    provider_id: str | None = None,
    q: str | None = None,
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    selected_provider = provider or provider_id
    return await ModelService(db).list(
        org_id,
        with_inactive=with_inactive,
        active=active,
        query=q,
        provider_id=selected_provider,
    )


@router.post("", response_model=ModelOut, status_code=201, dependencies=[Depends(require_permission("models:manage"))])
async def create_model(
    body: ModelCreate, org_id: str = Depends(get_current_org_id), db: AsyncSession = Depends(get_db)
):
    try:
        return await ModelService(db).create(org_id, body.model_dump())
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/{id}", response_model=ModelOut, dependencies=[Depends(require_permission("models:read"))])
async def get_model(
    id: str, org_id: str = Depends(get_current_org_id), db: AsyncSession = Depends(get_db)
):
    m = await ModelService(db).get(org_id, id)
    if m is None:
        raise HTTPException(404, "model not found")
    return m


@router.put("/{id}", response_model=ModelOut, dependencies=[Depends(require_permission("models:manage"))])
async def update_model(
    id: str,
    body: ModelUpdate,
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await ModelService(db).update(org_id, id, body.model_dump(exclude_unset=True))
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.delete("/{id}", dependencies=[Depends(require_permission("models:manage"))])
async def delete_model(
    id: str, org_id: str = Depends(get_current_org_id), db: AsyncSession = Depends(get_db)
):
    try:
        if not await ModelService(db).delete(org_id, id):
            raise HTTPException(404, "model not found")
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


@router.post("/{id}/test", response_model=ModelTestResult, dependencies=[Depends(require_permission("models:read"))])
async def test_model(
    id: str,
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await ModelService(db).test_chat(org_id, id)
    except ValueError as e:
        raise HTTPException(404, str(e))
