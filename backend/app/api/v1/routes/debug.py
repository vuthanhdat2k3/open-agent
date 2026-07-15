from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_api_key
from app.db.session import get_db
from app.services.debug_service import DebugService

router = APIRouter(
    prefix="/api/debug",
    tags=["debug"],
    dependencies=[Depends(verify_api_key)],
)


@router.get("/sessions")
async def list_sessions(db: AsyncSession = Depends(get_db)):
    return await DebugService(db).list_sessions()


@router.get("/sessions/{session_id}")
async def session_tree(session_id: str, db: AsyncSession = Depends(get_db)):
    try:
        return await DebugService(db).get_session_tree(session_id)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.get("/usage")
async def usage_summary(db: AsyncSession = Depends(get_db)):
    return await DebugService(db).usage_summary()


@router.get("/agents")
async def list_agents(db: AsyncSession = Depends(get_db)):
    return await DebugService(db).list_agents()
