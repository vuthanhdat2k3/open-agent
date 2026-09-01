from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authz.policy import PrincipalContext
from app.core.workflow.template_dags import TEMPLATE_DAGS
from app.db.base import gen_id, utc_now
from app.dependencies import get_current_org_id, get_current_user, get_db, require_permission
from app.models.user import User
from app.models.workflow import Workflow
from app.models.workflow_installation import WorkflowInstallation
from app.models.workflow_template import WorkflowTemplate, WorkflowTemplateVersion
from app.schemas.workflow_catalog import (
    WorkflowCatalogCapabilities,
    WorkflowCatalogItem,
    WorkflowCatalogMeta,
    WorkflowCatalogRecommendation,
    WorkflowCatalogResponse,
)

router = APIRouter(
    prefix="/api/workflow-catalog",
    tags=["workflow-catalog"],
)


@router.get(
    "/templates",
    response_model=WorkflowCatalogResponse,
    dependencies=[Depends(require_permission("workflows:read"))],
)
async def list_workflow_templates(
    query: str | None = Query(default=None, max_length=120),
    category: str | None = Query(default=None, max_length=48),
    org_id: str = Depends(get_current_org_id),
    current_user: User = Depends(get_current_user),
    principal: PrincipalContext = Depends(require_permission("workflows:read")),
    db: AsyncSession = Depends(get_db),
) -> WorkflowCatalogResponse:
    latest_version = (
        select(
            WorkflowTemplateVersion.template_id,
            func.max(WorkflowTemplateVersion.version).label("version"),
        )
        .join(WorkflowTemplate, WorkflowTemplate.id == WorkflowTemplateVersion.template_id)
        .where(WorkflowTemplate.status == "published", WorkflowTemplateVersion.published_at.is_not(None))
        .group_by(WorkflowTemplateVersion.template_id)
        .subquery()
    )
    filters = [
        WorkflowTemplate.status == "published",
        WorkflowTemplateVersion.published_at.is_not(None),
        WorkflowTemplateVersion.template_id == latest_version.c.template_id,
        WorkflowTemplateVersion.version == latest_version.c.version,
        or_(WorkflowTemplate.org_id.is_(None), WorkflowTemplate.org_id == org_id),
    ]
    if category:
        filters.append(WorkflowTemplateVersion.category == category)
    if query:
        pattern = f"%{query.strip()}%"
        filters.append(
            WorkflowTemplateVersion.name.ilike(pattern)
            | WorkflowTemplateVersion.description.ilike(pattern)
            | WorkflowTemplateVersion.outcome.ilike(pattern)
        )

    result = await db.execute(
        select(WorkflowTemplate, WorkflowTemplateVersion)
        .join(WorkflowTemplateVersion, WorkflowTemplateVersion.template_id == WorkflowTemplate.id)
        .where(and_(*filters))
        .order_by(WorkflowTemplateVersion.category, WorkflowTemplateVersion.name)
    )
    rows = result.all()

    # Determine which template keys this user has already installed (non-archived)
    installed_result = await db.execute(
        select(WorkflowInstallation.template_key)
        .where(
            WorkflowInstallation.org_id == org_id,
            WorkflowInstallation.owner_user_id == current_user.id,
            WorkflowInstallation.status != "archived",
        )
    )
    installed_keys: set[str] = set(installed_result.scalars().all())

    is_admin = principal.role in ("org_admin", "platform_admin")

    items = [
        WorkflowCatalogItem(
            key=template.key,
            version=version.version,
            name=version.name,
            description=version.description,
            outcome=version.outcome,
            category=version.category,
            icon=version.icon,
            required_integrations=version.required_integrations,
            optional_integrations=version.optional_integrations,
            default_schedule_label=version.default_schedule_label,
            cost_tier=version.cost_tier,
            estimated_cost_usd=version.estimated_cost_usd,
            side_effect_policy=version.side_effect_policy,
            recommendation=WorkflowCatalogRecommendation(
                recommended=version.recommendation_reason_code is not None,
                reason_code=version.recommendation_reason_code,
            ),
            installed=template.key in installed_keys,
            capabilities=WorkflowCatalogCapabilities(
                can_view=True,
                can_install=template.key not in installed_keys,
                can_delete=bool(
                    template.created_by_user_id is not None
                    and (template.created_by_user_id == current_user.id or is_admin)
                ),
            ),
            blocked_reasons={},
        )
        for template, version in rows
    ]
    return WorkflowCatalogResponse(
        data=items,
        meta=WorkflowCatalogMeta(server_time=utc_now()),
    )


class WorkflowPublishRequest(BaseModel):
    workflow_id: str = Field(..., description="ID of the workflow to publish to Marketplace")
    category: str = Field("custom", description="Category for the marketplace template")
    description: str | None = Field(None, description="Optional custom description")
    outcome: str | None = Field(None, description="Expected outcome summary")
    icon: str = Field("zap", description="Icon name for the marketplace card")


@router.post(
    "/publish",
    response_model=WorkflowCatalogItem,
    dependencies=[Depends(require_permission("workflows:update"))],
)
async def publish_workflow_to_catalog(
    body: WorkflowPublishRequest,
    org_id: str = Depends(get_current_org_id),
    current_user: User = Depends(get_current_user),
    principal: PrincipalContext = Depends(require_permission("workflows:update")),
    db: AsyncSession = Depends(get_db),
) -> WorkflowCatalogItem:
    # operators own marketplace publishing; admins grant it via ``*``.
    if not principal.allows("workflows:manage"):
        raise HTTPException(403, "Only operators can publish to the workflow marketplace")
    """Publish an organization workflow to the Workflow Marketplace (Operator/Admin)."""
    workflow = await db.scalar(
        select(Workflow).where(Workflow.id == body.workflow_id, Workflow.org_id == org_id)
    )
    if workflow is None:
        raise HTTPException(404, "workflow not found")

    template_key = f"market-{workflow.id[:12]}"
    template = await db.scalar(
        select(WorkflowTemplate).where(WorkflowTemplate.key == template_key)
    )
    if template is None:
        template = WorkflowTemplate(
            id=gen_id(),
            org_id=org_id,
            created_by_user_id=current_user.id,
            key=template_key,
            status="published",
        )
        db.add(template)
        await db.flush()
    else:
        if template.org_id is not None and template.org_id != org_id:
            raise HTTPException(403, "Cannot overwrite template from another organization")
        template.status = "published"
        template.org_id = org_id
        template.created_by_user_id = current_user.id

    version_row = await db.scalar(
        select(WorkflowTemplateVersion)
        .where(WorkflowTemplateVersion.template_id == template.id)
        .order_by(WorkflowTemplateVersion.version.desc())
        .limit(1)
    )
    next_ver = (version_row.version + 1) if version_row else 1

    new_version = WorkflowTemplateVersion(
        id=gen_id(),
        template_id=template.id,
        version=next_ver,
        name=workflow.name,
        description=body.description or workflow.description or "",
        outcome=body.outcome or workflow.description or "Custom organization automation.",
        category=body.category,
        icon=body.icon,
        published_at=utc_now(),
    )
    db.add(new_version)

    # Register graph in runtime TEMPLATE_DAGS map so it can be installed immediately
    TEMPLATE_DAGS[template_key] = {
        "kind": "catalog_template",
        "template_key": template_key,
        "template_version": next_ver,
        "nodes": (workflow.graph or {}).get("nodes", []),
        "edges": (workflow.graph or {}).get("edges", []),
    }

    await db.commit()

    return WorkflowCatalogItem(
        key=template.key,
        version=new_version.version,
        name=new_version.name,
        description=new_version.description,
        outcome=new_version.outcome,
        category=new_version.category,
        icon=new_version.icon,
        required_integrations=[],
        optional_integrations=[],
        default_schedule_label="",
        cost_tier="low",
        estimated_cost_usd={},
        side_effect_policy="safe",
        recommendation=WorkflowCatalogRecommendation(recommended=False, reason_code=None),
        capabilities=WorkflowCatalogCapabilities(can_view=True, can_install=True, can_delete=True),
        blocked_reasons={},
    )


@router.delete(
    "/templates/{key}",
    dependencies=[Depends(require_permission("workflows:delete"))],
)
async def unpublish_workflow_from_catalog(
    key: str,
    org_id: str = Depends(get_current_org_id),
    current_user: User = Depends(get_current_user),
    principal: PrincipalContext = Depends(require_permission("workflows:delete")),
    db: AsyncSession = Depends(get_db),
):
    # operators own marketplace publishing; admins grant it via ``*``.
    if not principal.allows("workflows:manage"):
        raise HTTPException(403, "Only operators can unpublish from the workflow marketplace")
    """Remove a published template from the Marketplace (Creator or Org Admin)."""
    # 1. Reject deletion of known system blueprints
    from app.core.workflow.templates import SYSTEM_WORKFLOW_BLUEPRINTS
    if key in SYSTEM_WORKFLOW_BLUEPRINTS:
        raise HTTPException(403, "System templates cannot be unpublished or deleted")

    template = await db.scalar(
        select(WorkflowTemplate).where(WorkflowTemplate.key == key)
    )
    if template is None:
        raise HTTPException(404, "Template not found")

    # Built-in system templates cannot be deleted by anyone
    if template.org_id is None or template.created_by_user_id is None:
        raise HTTPException(403, "System templates cannot be unpublished or deleted")

    # Organization scope check
    if template.org_id != org_id:
        raise HTTPException(404, "Template not found")

    # Creator or Org Admin check: Only the person who created/published it or an admin can delete it
    is_admin = principal.role in ("org_admin", "platform_admin")
    is_creator = template.created_by_user_id == current_user.id
    if not (is_creator or is_admin):
        raise HTTPException(403, "Only the creator or an organization admin can unpublish this template")

    template.status = "archived"
    TEMPLATE_DAGS.pop(key, None)
    await db.commit()
    return {"ok": True}
