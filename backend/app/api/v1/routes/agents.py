from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_api_key
from app.db.session import get_db
from app.schemas.agent import AgentCreate, AgentOut, AgentToolInfo, AgentUpdate
from app.services.agent_service import AgentService

router = APIRouter(
    prefix="/api/agents",
    tags=["agents"],
    dependencies=[Depends(verify_api_key)],
)


@router.get("", response_model=list[AgentOut])
async def list_agents(db: AsyncSession = Depends(get_db)):
    return await AgentService(db).list()


@router.get("/tools", response_model=list[AgentToolInfo])
async def list_tools(db: AsyncSession = Depends(get_db)):
    return await AgentService(db).list_available_tools()


@router.post("", response_model=AgentOut, status_code=201)
async def create_agent(body: AgentCreate, db: AsyncSession = Depends(get_db)):
    try:
        return await AgentService(db).create(body.model_dump())
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/{id}", response_model=AgentOut)
async def get_agent(id: str, db: AsyncSession = Depends(get_db)):
    a = await AgentService(db).get(id)
    if a is None:
        raise HTTPException(404, "agent not found")
    return a


@router.put("/{id}", response_model=AgentOut)
async def update_agent(
    id: str, body: AgentUpdate, db: AsyncSession = Depends(get_db)
):
    try:
        return await AgentService(db).update(id, body.model_dump(exclude_unset=True))
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.delete("/{id}")
async def delete_agent(id: str, db: AsyncSession = Depends(get_db)):
    if not await AgentService(db).delete(id):
        raise HTTPException(404, "agent not found")
    return {"ok": True}
