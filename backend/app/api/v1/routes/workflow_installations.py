from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import gen_id
from app.db.session import get_db
from app.dependencies import get_current_org_id, get_current_user, require_permission
from app.models.user import User
from app.models.workflow import Workflow
from app.models.workflow_installation import WorkflowInstallation
from app.models.workflow_template import WorkflowTemplate, WorkflowTemplateVersion
from app.schemas.workflow_installation import (
    InstallationCapabilities,
    InstallationCreate,
    InstallationOut,
)

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
        capabilities=InstallationCapabilities(can_resume=paused, can_pause=not paused),
        blocked_reasons={},
    )


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
        settings=body.settings,
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
