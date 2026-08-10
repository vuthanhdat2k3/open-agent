from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.observability.audit import log_action
from app.core.quota.dependencies import enforce_resource_quota
from app.dependencies import get_current_org_id, get_current_user, get_db, require_permission
from app.models.membership import Membership
from app.models.role import Role
from app.models.user import User
from app.schemas.agent import (
    AgentCreate,
    AgentOut,
    AgentReleaseCreate,
    AgentReleaseOut,
    AgentToolInfo,
    AgentUpdate,
)
from app.services.agent_service import AgentService, QualityGateBlocked

router = APIRouter(
    prefix="/api/agents",
    tags=["agents"],
)


class PublishReleaseRequest(BaseModel):
    # Publishing over a failing quality gate. Opt-in, owner-only, audited.
    force: bool = False


def _release_error(exc: ValueError) -> HTTPException:
    detail = str(exc)
    return HTTPException(404 if "not found" in detail else 400, detail)


async def _is_admin(db: AsyncSession, org_id: str, user_id: str | None) -> bool:
    if not user_id:
        return False
    result = await db.execute(
        select(Membership).where(
            Membership.org_id == org_id, Membership.user_id == user_id
        )
    )
    membership = result.scalar_one_or_none()
    return membership is not None and membership.role == Role.admin


@router.get("", response_model=list[AgentOut], dependencies=[Depends(require_permission("agents:read"))])
async def list_agents(
    request: Request,
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    agents = await AgentService(db).list(org_id)
    user_id = getattr(request.state, "user_id", None)
    # A plain "user" role only ever sees the org's primary (orchestrator-kind)
    # agent(s) - worker agents are implementation detail the orchestrator
    # delegates to internally via call_agent, not something a user picks
    # directly. Admin sees everything (needed to build/test each agent).
    if not await _is_admin(db, org_id, user_id):
        agents = [a for a in agents if a.kind == "orchestrator"]
    return agents


@router.get("/tools", response_model=list[AgentToolInfo], dependencies=[Depends(require_permission("agents:read"))])
async def list_tools(
    org_id: str = Depends(get_current_org_id),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await AgentService(db).list_available_tools(org_id, current_user.id)


@router.post(
    "",
    response_model=AgentOut,
    status_code=201,
    dependencies=[
        Depends(require_permission("agents:create")),
        Depends(enforce_resource_quota("agents")),
    ],
)
async def create_agent(
    body: AgentCreate,
    request: Request,
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    user_id = getattr(request.state, "user_id", None)
    try:
        agent = await AgentService(db).create(org_id, body.model_dump(), user_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    await log_action(
        db,
        org_id=org_id,
        actor_user_id=user_id,
        action="agent.release.publish",
        resource_type="agent_release",
        resource_id=agent.active_release_id,
        metadata={"agent_id": agent.id, "version": 1, "initial": True},
    )
    return agent


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
    request: Request,
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    user_id = getattr(request.state, "user_id", None)
    service = AgentService(db)
    current = await service.get(org_id, id)
    previous_release_number = current.latest_release_number if current else None
    try:
        agent = await service.update(
            org_id,
            id,
            body.model_dump(exclude_unset=True),
            user_id,
        )
    except ValueError as e:
        raise HTTPException(404, str(e))
    if agent.latest_release_number != previous_release_number:
        await log_action(
            db,
            org_id=org_id,
            actor_user_id=user_id,
            action="agent.release.publish",
            resource_type="agent_release",
            resource_id=agent.active_release_id,
            metadata={"agent_id": agent.id, "version": agent.latest_release_number},
        )
    return agent


@router.get(
    "/{id}/releases",
    response_model=list[AgentReleaseOut],
    dependencies=[Depends(require_permission("agents:read"))],
)
async def list_agent_releases(
    id: str,
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await AgentService(db).list_releases(org_id, id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post(
    "/{id}/releases",
    response_model=AgentReleaseOut,
    status_code=201,
    dependencies=[Depends(require_permission("agents:update"))],
)
async def create_agent_release(
    id: str,
    body: AgentReleaseCreate,
    request: Request,
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    user_id = getattr(request.state, "user_id", None)
    try:
        release = await AgentService(db).create_release(
            org_id,
            id,
            body.model_dump(exclude_none=True),
            user_id,
        )
    except ValueError as exc:
        raise _release_error(exc) from exc
    await log_action(
        db,
        org_id=org_id,
        actor_user_id=user_id,
        action="agent.release.create",
        resource_type="agent_release",
        resource_id=release.id,
        metadata={"agent_id": id, "version": release.version},
    )
    return release


@router.get(
    "/{id}/releases/{version}",
    response_model=AgentReleaseOut,
    dependencies=[Depends(require_permission("agents:read"))],
)
async def get_agent_release(
    id: str,
    version: int,
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    release = await AgentService(db).get_release(org_id, id, version)
    if release is None:
        raise HTTPException(404, "agent release not found")
    return release


@router.post(
    "/{id}/releases/{version}/publish",
    response_model=AgentReleaseOut,
    dependencies=[Depends(require_permission("agents:publish"))],
)
async def publish_agent_release(
    id: str,
    version: int,
    request: Request,
    body: PublishReleaseRequest | None = None,
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    user_id = getattr(request.state, "user_id", None)
    force = bool(body and body.force)

    if force and not await _is_admin(db, org_id, user_id):
        # Shipping over a red gate is an owner-level decision, not something
        # anyone holding publish rights may do.
        raise HTTPException(403, "only an organization admin may force publish")

    try:
        release = await AgentService(db).publish_release(
            org_id, id, version, user_id, force=force
        )
    except QualityGateBlocked as exc:
        raise HTTPException(
            409,
            {
                "message": str(exc),
                "quality_gate_run_id": exc.run_id,
                "pass_rate": exc.pass_rate,
                "min_pass_rate": exc.min_pass_rate,
                "hint": "an owner may retry with force=true",
            },
        ) from exc
    except ValueError as exc:
        raise _release_error(exc) from exc

    if force and release.quality_gate_status == "failed":
        # Logged separately from the publish event: overriding a failing gate
        # is precisely what an auditor comes looking for.
        await log_action(
            db,
            org_id=org_id,
            actor_user_id=user_id,
            action="agent.release.gate_overridden",
            resource_type="agent_release",
            resource_id=release.id,
            metadata={
                "agent_id": id,
                "version": release.version,
                "quality_gate_run_id": release.quality_gate_run_id,
            },
        )

    await log_action(
        db,
        org_id=org_id,
        actor_user_id=user_id,
        action="agent.release.publish",
        resource_type="agent_release",
        resource_id=release.id,
        metadata={
            "agent_id": id,
            "version": release.version,
            "quality_gate_status": release.quality_gate_status,
            "forced": force,
        },
    )
    return release


@router.post(
    "/{id}/releases/{version}/rollback",
    response_model=AgentReleaseOut,
    status_code=201,
    dependencies=[Depends(require_permission("agents:publish"))],
)
async def rollback_agent_release(
    id: str,
    version: int,
    request: Request,
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    user_id = getattr(request.state, "user_id", None)
    try:
        release = await AgentService(db).rollback_release(
            org_id, id, version, user_id
        )
    except ValueError as exc:
        raise _release_error(exc) from exc
    await log_action(
        db,
        org_id=org_id,
        actor_user_id=user_id,
        action="agent.release.rollback",
        resource_type="agent_release",
        resource_id=release.id,
        metadata={"agent_id": id, "version": release.version, "target_version": version},
    )
    return release


@router.delete("/{id}", dependencies=[Depends(require_permission("agents:delete"))])
async def delete_agent(
    id: str, org_id: str = Depends(get_current_org_id), db: AsyncSession = Depends(get_db)
):
    try:
        if not await AgentService(db).delete(org_id, id):
            raise HTTPException(404, "agent not found")
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}
