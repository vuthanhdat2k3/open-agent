from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_org_id, get_db, require_permission
from app.schemas.agent import AgentCreate, AgentOut, AgentToolInfo, AgentUpdate
from app.services.agent_service import AgentService

router = APIRouter(
    prefix="/api/agents",
    tags=["agents"],
)


@router.get("", response_model=list[AgentOut], dependencies=[Depends(require_permission("agents:read"))])
async def list_agents(
    org_id: str = Depends(get_current_org_id), db: AsyncSession = Depends(get_db)
):
    return await AgentService(db).list(org_id)


@router.get("/tools", response_model=list[AgentToolInfo], dependencies=[Depends(require_permission("agents:read"))])
async def list_tools(org_id: str = Depends(get_current_org_id), db: AsyncSession = Depends(get_db)):
    return await AgentService(db).list_available_tools(org_id)


@router.post("", response_model=AgentOut, status_code=201, dependencies=[Depends(require_permission("agents:create"))])
async def create_agent(
    body: AgentCreate, org_id: str = Depends(get_current_org_id), db: AsyncSession = Depends(get_db)
):
    try:
        return await AgentService(db).create(org_id, body.model_dump())
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/{id}", response_model=AgentOut, dependencies=[Depends(require_permission("agents:read"))])
async def get_agent(
    id: str, org_id: str = Depends(get_current_org_id), db: AsyncSession = Depends(get_db)
):
    a = await AgentService(db).get(org_id, id)
    if a is None:
        raise HTTPException(404, "agent not found")
    return a


@router.put("/{id}", response_model=AgentOut, dependencies=[Depends(require_permission("agents:update"))])
async def update_agent(
    id: str,
    body: AgentUpdate,
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await AgentService(db).update(org_id, id, body.model_dump(exclude_unset=True))
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.delete("/{id}", dependencies=[Depends(require_permission("agents:delete"))])
async def delete_agent(
    id: str, org_id: str = Depends(get_current_org_id), db: AsyncSession = Depends(get_db)
):
    if not await AgentService(db).delete(org_id, id):
        raise HTTPException(404, "agent not found")
    return {"ok": True}
