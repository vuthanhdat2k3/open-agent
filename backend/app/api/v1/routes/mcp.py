from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_api_key
from app.db.session import get_db
from app.schemas.mcp import McpServerCreate, McpServerOut, McpServerUpdate
from app.services.mcp_service import McpService

router = APIRouter(
    prefix="/api/mcp/servers",
    tags=["mcp"],
    dependencies=[Depends(verify_api_key)],
)


@router.get("", response_model=list[McpServerOut])
async def list_servers(db: AsyncSession = Depends(get_db)):
    return await McpService(db).list()


@router.post("", response_model=McpServerOut, status_code=201)
async def create_server(body: McpServerCreate, db: AsyncSession = Depends(get_db)):
    try:
        return await McpService(db).create(body.model_dump())
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.get("/{id}", response_model=McpServerOut)
async def get_server(id: str, db: AsyncSession = Depends(get_db)):
    s = await McpService(db).get(id)
    if s is None:
        raise HTTPException(404, "mcp server not found")
    return s


@router.put("/{id}", response_model=McpServerOut)
async def update_server(
    id: str, body: McpServerUpdate, db: AsyncSession = Depends(get_db)
):
    try:
        return await McpService(db).update(id, body.model_dump(exclude_unset=True))
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.delete("/{id}")
async def delete_server(id: str, db: AsyncSession = Depends(get_db)):
    if not await McpService(db).delete(id):
        raise HTTPException(404, "mcp server not found")
    return {"ok": True}


@router.post("/{id}/connect")
async def connect(id: str, db: AsyncSession = Depends(get_db)):
    return await McpService(db).connect(id)


@router.post("/{id}/disconnect")
async def disconnect(id: str, db: AsyncSession = Depends(get_db)):
    return await McpService(db).disconnect(id)
