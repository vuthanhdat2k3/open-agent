from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_org_id, get_db, require_permission
from app.services.debug_service import DebugService

router = APIRouter(
    prefix="/api/debug",
    tags=["debug"],
)


@router.get("/sessions", dependencies=[Depends(require_permission("usage:read"))])
async def list_sessions(
    org_id: str = Depends(get_current_org_id), db: AsyncSession = Depends(get_db)
):
    return await DebugService(db).list_sessions(org_id)


@router.get("/sessions/{session_id}", dependencies=[Depends(require_permission("usage:read"))])
async def session_tree(
    session_id: str,
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await DebugService(db).get_session_tree(org_id, session_id)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.get("/usage", dependencies=[Depends(require_permission("usage:read"))])
async def usage_summary(
    org_id: str = Depends(get_current_org_id), db: AsyncSession = Depends(get_db)
):
    return await DebugService(db).usage_summary(org_id)


@router.get("/agents", dependencies=[Depends(require_permission("agents:read"))])
async def list_agents(
    org_id: str = Depends(get_current_org_id), db: AsyncSession = Depends(get_db)
):
    return await DebugService(db).list_agents(org_id)
