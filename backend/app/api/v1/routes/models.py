from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_api_key
from app.db.session import get_db
from app.schemas.model import ModelCreate, ModelOut, ModelUpdate
from app.services.model_service import ModelService

router = APIRouter(
    prefix="/api/models",
    tags=["models"],
    dependencies=[Depends(verify_api_key)],
)


@router.get("", response_model=list[ModelOut])
async def list_models(db: AsyncSession = Depends(get_db)):
    return await ModelService(db).list()


@router.post("", response_model=ModelOut, status_code=201)
async def create_model(body: ModelCreate, db: AsyncSession = Depends(get_db)):
    try:
        return await ModelService(db).create(body.model_dump())
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/{id}", response_model=ModelOut)
async def get_model(id: str, db: AsyncSession = Depends(get_db)):
    m = await ModelService(db).get(id)
    if m is None:
        raise HTTPException(404, "model not found")
    return m


@router.put("/{id}", response_model=ModelOut)
async def update_model(
    id: str, body: ModelUpdate, db: AsyncSession = Depends(get_db)
):
    try:
        return await ModelService(db).update(id, body.model_dump(exclude_unset=True))
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.delete("/{id}")
async def delete_model(id: str, db: AsyncSession = Depends(get_db)):
    if not await ModelService(db).delete(id):
        raise HTTPException(404, "model not found")
    return {"ok": True}
