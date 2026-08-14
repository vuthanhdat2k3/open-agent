from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import gen_id, utc_now
from app.db.session import get_db
from app.dependencies import get_current_org_id, get_current_user, require_permission
from app.models.customer_intelligence import EmailConnection
from app.models.outbox import OutboxEvent
from app.models.user import User
from app.models.workflow import Workflow
from app.models.workflow_installation import WorkflowInstallation
from app.models.workflow_occurrence import WorkflowOccurrence
from app.models.workflow_run import WorkflowRun
from app.models.workflow_template import WorkflowTemplate, WorkflowTemplateVersion
from app.schemas.workflow_installation import (
    InstallationCapabilities,
    InstallationCreate,
    InstallationOut,
)
from app.workflows.scheduler import next_run_at

router = APIRouter(prefix="/api/workflow-catalog", tags=["workflow-installations"])


def _out(item: WorkflowInstallation) -> InstallationOut:
    paused = item.status == "paused"
    return InstallationOut(
        id=item.id,
        template_key=item.template_key,
        template_version=item.template_version,
        workflow_id=item.workflow_id,
        name=item.name,
        status=item.status,
        timezone=item.timezone,
        schedule=item.schedule,
        settings=item.settings,
        created_at=item.created_at,
        updated_at=item.updated_at,
        capabilities=InstallationCapabilities(can_resume=paused, can_pause=not paused, can_run_now=True),
        blocked_reasons={},
    )


@router.get("/activity", dependencies=[Depends(require_permission("workflows:read"))])
async def list_workflow_activity(
    org_id: str = Depends(get_current_org_id),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = 25,
):
    limit = max(1, min(limit, 50))
    rows = await db.execute(
        select(WorkflowOccurrence, WorkflowInstallation, WorkflowRun)
        .join(WorkflowInstallation, WorkflowInstallation.id == WorkflowOccurrence.installation_id)
        .join(WorkflowRun, WorkflowRun.id == WorkflowOccurrence.workflow_run_id)
        .where(WorkflowInstallation.org_id == org_id, WorkflowInstallation.owner_user_id == current_user.id)
        .order_by(WorkflowOccurrence.scheduled_for.desc(), WorkflowOccurrence.id.desc())
        .limit(limit)
    )
    return {
        "items": [
            {
                "id": occurrence.id,
                "installation_id": installation.id,
                "template_key": installation.template_key,
                "name": installation.name,
                "scheduled_for": occurrence.scheduled_for,
                "status": run.status,
                "output": run.output or {},
                "error": run.error,
                "created_at": occurrence.created_at,
            }
            for occurrence, installation, run in rows.all()
        ],
        "meta": {"server_time": utc_now().isoformat()},
    }


@router.get("/installations", response_model=list[InstallationOut], dependencies=[Depends(require_permission("workflows:read"))])
async def list_installations(
    org_id: str = Depends(get_current_org_id),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(WorkflowInstallation)
        .where(WorkflowInstallation.org_id == org_id, WorkflowInstallation.owner_user_id == current_user.id)
        .order_by(WorkflowInstallation.updated_at.desc())
    )
    return [_out(item) for item in result.scalars().all()]


@router.post(
    "/installations",
    response_model=InstallationOut,
    status_code=201,
    dependencies=[Depends(require_permission("workflows:install"))],
)
async def install_template(
    body: InstallationCreate,
    org_id: str = Depends(get_current_org_id),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    template_result = await db.execute(
        select(WorkflowTemplate, WorkflowTemplateVersion)
        .join(WorkflowTemplateVersion, WorkflowTemplateVersion.template_id == WorkflowTemplate.id)
        .where(
            WorkflowTemplate.key == body.template_key,
            WorkflowTemplate.status == "published",
            WorkflowTemplateVersion.published_at.is_not(None),
        )
        .order_by(WorkflowTemplateVersion.version.desc())
        .limit(1)
    )
    template_pair = template_result.first()
    if template_pair is None:
        raise HTTPException(404, "workflow template not found")
    _template, version = template_pair

    settings = dict(body.settings)
    if body.template_key == "gmail_monitor_and_triage":
        connection = await db.scalar(
            select(EmailConnection).where(
                EmailConnection.org_id == org_id,
                EmailConnection.created_by_user_id == current_user.id,
                EmailConnection.provider == "gmail",
                EmailConnection.status == "connected",
            ).order_by(EmailConnection.created_at.desc())
        )
        if connection is None:
            raise HTTPException(409, "connect Gmail before enabling this workflow")
        settings["connection_id"] = connection.id

    existing = await db.scalar(
        select(WorkflowInstallation).where(
            WorkflowInstallation.org_id == org_id,
            WorkflowInstallation.owner_user_id == current_user.id,
            WorkflowInstallation.template_key == body.template_key,
        )
    )
    if existing is not None:
        raise HTTPException(409, "workflow template is already installed")

    installation_id = gen_id()
    workflow = Workflow(
        id=gen_id(),
        org_id=org_id,
        created_by_user_id=current_user.id,
        name=body.name or version.name,
        description=f"Managed installation of {version.name}",
        graph={"nodes": [{"id": "input", "kind": "input", "label": "Trigger"}, {"id": "output", "kind": "output", "label": "Result"}], "edges": [{"from_": "input", "to": "output"}]},
    )
    installation = WorkflowInstallation(
        id=installation_id,
        org_id=org_id,
        owner_user_id=current_user.id,
        template_key=body.template_key,
        template_version=version.version,
        workflow_id=workflow.id,
        name=body.name or version.name,
        status="enabled",
        timezone=body.timezone,
        schedule=body.schedule.model_dump(),
        settings=settings,
        next_run_at=next_run_at(body.schedule.model_dump(), body.timezone),
    )
    db.add(workflow)
    db.add(installation)
    await db.commit()
    await db.refresh(installation)
    return _out(installation)


@router.get("/installations/{installation_id}", response_model=InstallationOut, dependencies=[Depends(require_permission("workflows:read"))])
async def get_installation(
    installation_id: str,
    org_id: str = Depends(get_current_org_id),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    item = await db.scalar(select(WorkflowInstallation).where(WorkflowInstallation.id == installation_id, WorkflowInstallation.org_id == org_id, WorkflowInstallation.owner_user_id == current_user.id))
    if item is None:
        raise HTTPException(404, "workflow installation not found")
    return _out(item)


@router.post("/installations/{installation_id}/run", response_model=InstallationOut, dependencies=[Depends(require_permission("workflows:run"))])
async def run_installation_now(
    installation_id: str,
    org_id: str = Depends(get_current_org_id),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    item = await db.scalar(select(WorkflowInstallation).where(WorkflowInstallation.id == installation_id, WorkflowInstallation.org_id == org_id, WorkflowInstallation.owner_user_id == current_user.id))
    if item is None:
        raise HTTPException(404, "workflow installation not found")
    now = utc_now()
    occurrence_id = gen_id()
    run_id = gen_id()
    db.add(WorkflowRun(id=run_id, org_id=org_id, workflow_id=item.workflow_id, status="queued", input={"text": "", "timezone": item.timezone, "trigger": "manual", "installation_id": item.id}, triggered_by_user_id=current_user.id))
    db.add(WorkflowOccurrence(id=occurrence_id, installation_id=item.id, workflow_run_id=run_id, occurrence_key=f"manual:{occurrence_id}", scheduled_for=now, status="queued", payload={"template_key": item.template_key, "trigger": "manual"}))
    db.add(OutboxEvent(event_type="workflow.run.requested", aggregate_type="workflow_occurrence", aggregate_id=occurrence_id, org_id=org_id, user_id=current_user.id, correlation_id=occurrence_id, payload={"run_id": run_id, "installation_id": item.id}, dedupe_key=f"manual:{occurrence_id}"))
    await db.commit()
    await db.refresh(item)
    return _out(item)


@router.post("/installations/{installation_id}/pause", response_model=InstallationOut, dependencies=[Depends(require_permission("workflows:install"))])
async def pause_installation(
    installation_id: str,
    org_id: str = Depends(get_current_org_id),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    item = await db.scalar(select(WorkflowInstallation).where(WorkflowInstallation.id == installation_id, WorkflowInstallation.org_id == org_id, WorkflowInstallation.owner_user_id == current_user.id))
    if item is None:
        raise HTTPException(404, "workflow installation not found")
    item.status = "paused"
    item.next_run_at = None
    await db.commit()
    await db.refresh(item)
    return _out(item)


@router.post("/installations/{installation_id}/resume", response_model=InstallationOut, dependencies=[Depends(require_permission("workflows:install"))])
async def resume_installation(
    installation_id: str,
    org_id: str = Depends(get_current_org_id),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    item = await db.scalar(select(WorkflowInstallation).where(WorkflowInstallation.id == installation_id, WorkflowInstallation.org_id == org_id, WorkflowInstallation.owner_user_id == current_user.id))
    if item is None:
        raise HTTPException(404, "workflow installation not found")
    item.status = "enabled"
    item.next_run_at = next_run_at(item.schedule, item.timezone)
    await db.commit()
    await db.refresh(item)
    return _out(item)


@router.delete("/installations/{installation_id}", status_code=204, dependencies=[Depends(require_permission("workflows:install"))])
async def delete_installation(
    installation_id: str,
    org_id: str = Depends(get_current_org_id),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    item = await db.scalar(select(WorkflowInstallation).where(WorkflowInstallation.id == installation_id, WorkflowInstallation.org_id == org_id, WorkflowInstallation.owner_user_id == current_user.id))
    if item is None:
        raise HTTPException(404, "workflow installation not found")
    await db.delete(item)
    await db.commit()
