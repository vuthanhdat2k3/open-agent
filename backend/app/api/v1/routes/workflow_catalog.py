from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utc_now
from app.dependencies import get_current_org_id, get_db, require_permission
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
    db: AsyncSession = Depends(get_db),
) -> WorkflowCatalogResponse:
    # The catalog is system-owned. org_id is intentionally resolved and kept in
    # the route contract so future installation/capability checks cannot forget
    # tenant context.
    del org_id
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
            capabilities=WorkflowCatalogCapabilities(can_view=True, can_install=True),
            blocked_reasons={},
        )
        for template, version in rows
    ]
    return WorkflowCatalogResponse(
        data=items,
        meta=WorkflowCatalogMeta(server_time=utc_now()),
    )
