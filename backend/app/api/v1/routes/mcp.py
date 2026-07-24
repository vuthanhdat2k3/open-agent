from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_org_id, get_db, require_permission
from app.schemas.mcp import McpServerCreate, McpServerOut, McpServerUpdate
from app.services.mcp_service import McpService

router = APIRouter(
    prefix="/api/mcp/servers",
    tags=["mcp"],
)


@router.get("", response_model=list[McpServerOut], dependencies=[Depends(require_permission("mcp:read"))])
async def list_servers(
    org_id: str = Depends(get_current_org_id), db: AsyncSession = Depends(get_db)
):
    return await McpService(db).list(org_id)


@router.post("", response_model=McpServerOut, status_code=201, dependencies=[Depends(require_permission("mcp:manage"))])
async def create_server(
    body: McpServerCreate,
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await McpService(db).create(org_id, body.model_dump())
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.get("/{id}", response_model=McpServerOut, dependencies=[Depends(require_permission("mcp:read"))])
async def get_server(
    id: str, org_id: str = Depends(get_current_org_id), db: AsyncSession = Depends(get_db)
):
    s = await McpService(db).get(org_id, id)
    if s is None:
        raise HTTPException(404, "mcp server not found")
    return s


@router.put("/{id}", response_model=McpServerOut, dependencies=[Depends(require_permission("mcp:manage"))])
async def update_server(
    id: str,
    body: McpServerUpdate,
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await McpService(db).update(org_id, id, body.model_dump(exclude_unset=True))
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.delete("/{id}", dependencies=[Depends(require_permission("mcp:manage"))])
async def delete_server(
    id: str, org_id: str = Depends(get_current_org_id), db: AsyncSession = Depends(get_db)
):
    if not await McpService(db).delete(org_id, id):
        raise HTTPException(404, "mcp server not found")
    return {"ok": True}


@router.post("/{id}/connect", dependencies=[Depends(require_permission("mcp:manage"))])
async def connect(
    id: str, org_id: str = Depends(get_current_org_id), db: AsyncSession = Depends(get_db)
):
    return await McpService(db).connect(org_id, id)


@router.post("/{id}/disconnect", dependencies=[Depends(require_permission("mcp:manage"))])
async def disconnect(
    id: str, org_id: str = Depends(get_current_org_id), db: AsyncSession = Depends(get_db)
):
    return await McpService(db).disconnect(org_id, id)
