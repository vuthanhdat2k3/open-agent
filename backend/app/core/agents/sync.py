from __future__ import annotations

from dataclasses import dataclass

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.agents.templates import SYSTEM_AGENT_BLUEPRINTS, SystemAgentBlueprint
from app.db.base import gen_id, utc_now
from app.models.agent import Agent
from app.models.agent_release import AgentRelease
from app.models.model import Model
from app.models.org_agent_settings import OrgAgentSettings
from app.models.organization import Organization
from app.services.agent_service import AgentService, _config_hash, _snapshot

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class SystemAgentSyncResult:
    org_id: str
    created: int = 0
    updated: int = 0
    skipped: int = 0


def _apply_blueprint_to_agent(agent: Agent, blueprint: SystemAgentBlueprint) -> None:
    agent.name = blueprint.name
    agent.description = blueprint.description
    agent.system_prompt = blueprint.system_prompt
    agent.tools = list(blueprint.tools)
    agent.allowed_risk_tiers = list(blueprint.allowed_risk_tiers)
    agent.kind = blueprint.kind
    agent.max_iterations = blueprint.max_iterations
    agent.temperature = blueprint.temperature
    agent.enable_thinking = blueprint.enable_thinking
    agent.a2a_exposed = blueprint.a2a_exposed
    agent.auto_rollback_enabled = blueprint.auto_rollback_enabled
    agent.template_key = blueprint.key
    agent.is_customized = False


async def _create_blueprint_agent(
    db: AsyncSession,
    org_id: str,
    blueprint: SystemAgentBlueprint,
    *,
    model_id: str,
    temperature: float,
    agent_id: str | None = None,
) -> Agent:
    if not agent_id:
        existing_id = await db.scalar(select(Agent.id).where(Agent.id == blueprint.id))
        agent_id = blueprint.id if existing_id is None else gen_id()

    persisted = Agent(
        id=agent_id,
        org_id=org_id,
        created_by_user_id=None,
        name=blueprint.name,
        description=blueprint.description,
        system_prompt=blueprint.system_prompt,
        model_id=model_id,
        tools=list(blueprint.tools),
        allowed_risk_tiers=list(blueprint.allowed_risk_tiers),
        kind=blueprint.kind,
        max_iterations=blueprint.max_iterations,
        temperature=temperature,
        enable_thinking=blueprint.enable_thinking,
        a2a_exposed=blueprint.a2a_exposed,
        auto_rollback_enabled=blueprint.auto_rollback_enabled,
        template_key=blueprint.key,
        is_customized=False,
    )
    db.add(persisted)
    await db.flush()
    release_config = _snapshot(persisted)
    release = AgentRelease(
        id=gen_id(),
        org_id=org_id,
        agent_id=persisted.id,
        version=1,
        status="published",
        **release_config,
        change_note="System blueprint startup sync",
        config_hash=_config_hash(release_config),
        published_at=utc_now(),
    )
    db.add(release)
    await db.flush()
    persisted.active_release_id = release.id
    persisted.latest_release_number = 1
    return persisted


async def sync_system_agents_for_org(
    db: AsyncSession,
    org_id: str,
    *,
    service: AgentService | None = None,
) -> SystemAgentSyncResult:
    """Ensure every enabled system blueprint exists as a DB row for one org."""
    agent_service = service or AgentService(db)

    settings_res = await db.execute(
        select(OrgAgentSettings).where(OrgAgentSettings.org_id == org_id)
    )
    settings_by_key = {row.template_key: row for row in settings_res.scalars().all()}

    existing_res = await db.execute(
        select(Agent).where(Agent.org_id == org_id, Agent.template_key.is_not(None))
    )
    existing_by_key = {agent.template_key: agent for agent in existing_res.scalars().all() if agent.template_key}

    models_res = await db.execute(
        select(Model).where(Model.org_id == org_id, Model.active.is_(True))
    )
    active_models = list(models_res.scalars().all())

    created = 0
    updated = 0
    skipped = 0

    for blueprint in SYSTEM_AGENT_BLUEPRINTS.values():
        settings = settings_by_key.get(blueprint.key)
        if settings is not None and not settings.is_enabled:
            skipped += 1
            continue

        model_id = (
            settings.model_override_id
            if settings is not None and settings.model_override_id
            else await agent_service._resolve_model_for_tier(org_id, blueprint.recommended_tier, active_models)
        )
        if not model_id:
            skipped += 1
            await logger.awarning(
                "system_agent_sync_skipped_no_model",
                org_id=org_id,
                template_key=blueprint.key,
            )
            continue

        temperature = (
            settings.temperature_override
            if settings is not None and settings.temperature_override is not None
            else blueprint.temperature
        )

        existing = existing_by_key.get(blueprint.key)
        if existing is None:
            try:
                async with db.begin_nested():
                    existing = await _create_blueprint_agent(
                        db,
                        org_id,
                        blueprint,
                        model_id=model_id,
                        temperature=temperature,
                    )
                created += 1
                existing_by_key[blueprint.key] = existing
            except IntegrityError:
                existing = await db.scalar(
                    select(Agent).where(Agent.org_id == org_id, Agent.template_key == blueprint.key)
                )
                if existing is None:
                    # Retry with a guaranteed unique UUID in case of PK collision from another org
                    async with db.begin_nested():
                        existing = await _create_blueprint_agent(
                            db,
                            org_id,
                            blueprint,
                            model_id=model_id,
                            temperature=temperature,
                            agent_id=gen_id(),
                        )
                    created += 1
                existing_by_key[blueprint.key] = existing
            else:
                continue

        if existing is None:
            continue

        if getattr(existing, "is_customized", True):
            skipped += 1
            continue

        previous = _snapshot(existing)
        _apply_blueprint_to_agent(existing, blueprint)
        existing.model_id = model_id
        existing.temperature = temperature
        if previous != _snapshot(existing):
            updated += 1

    return SystemAgentSyncResult(org_id=org_id, created=created, updated=updated, skipped=skipped)


async def sync_system_agents_all_orgs(db: AsyncSession) -> list[SystemAgentSyncResult]:
    """Sync enabled system blueprints for every active organization."""
    org_ids = (
        await db.scalars(
            select(Organization.id).where(Organization.lifecycle_status != "deleted")
        )
    ).all()
    results: list[SystemAgentSyncResult] = []
    for org_id in org_ids:
        result = await sync_system_agents_for_org(db, org_id)
        results.append(result)
        if result.created or result.updated:
            await logger.ainfo(
                "system_agents_synced",
                org_id=org_id,
                created=result.created,
                updated=result.updated,
                skipped=result.skipped,
            )
    await db.commit()
    return results
