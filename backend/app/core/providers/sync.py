from __future__ import annotations

import os
from dataclasses import dataclass

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.credential_secrets import encrypt_string
from app.core.providers.templates import get_templates
from app.db.base import gen_id, utc_now
from app.models.model import Model
from app.models.organization import Organization
from app.models.provider import Provider

logger = structlog.get_logger(__name__)

_ENV_VARS: dict[str, str] = {
    "openai": "OPENAI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "ollama": "OLLAMA_API_KEY",
    "gemini": "GOOGLE_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "opencode": "OPENCODE_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
}


@dataclass(frozen=True)
class SystemProviderSyncResult:
    org_id: str
    created: int
    skipped: int
    models_created: int


async def sync_system_providers_for_org(
    db: AsyncSession,
    org_id: str,
) -> SystemProviderSyncResult:
    """Ensure standard provider templates and fallback models exist for one organization.

    NON-DESTRUCTIVE: If a provider already exists for this org, preserves 100% of user
    modifications (custom base_url, custom API keys, customized models, is_default, etc.).
    """
    templates = get_templates()

    # Query existing providers for this org
    existing_providers_res = await db.execute(
        select(Provider).where(Provider.org_id == org_id)
    )
    existing_providers = list(existing_providers_res.scalars().all())
    existing_by_key = {p.key: p for p in existing_providers}
    existing_by_tpl = {p.template_key: p for p in existing_providers if p.template_key}

    has_default = any(p.is_default for p in existing_providers)

    created_count = 0
    skipped_count = 0
    models_created_count = 0
    now = utc_now()

    for template in templates:
        existing = existing_by_tpl.get(template.key) or existing_by_key.get(template.key)

        if existing is not None:
            # NON-DESTRUCTIVE: keep user's existing provider configuration completely intact!
            skipped_count += 1
            # Check if this existing provider is missing fallback models in models table
            existing_models_res = await db.execute(
                select(Model).where(Model.org_id == org_id, Model.provider_id == existing.id)
            )
            existing_model_names = {m.name for m in existing_models_res.scalars().all()}
            for f_spec in template.fallback_models:
                if f_spec.name not in existing_model_names:
                    new_model = Model(
                        id=gen_id(),
                        org_id=org_id,
                        provider_id=existing.id,
                        name=f_spec.name,
                        display_name=f_spec.display_name,
                        context_window=f_spec.context_window,
                        input_cost_per_1k=f_spec.input_cost_per_1k,
                        output_cost_per_1k=f_spec.output_cost_per_1k,
                        supports_tools=f_spec.supports_tools if f_spec.supports_tools is not None else template.supports_tools,
                        supports_reasoning=f_spec.supports_reasoning if f_spec.supports_reasoning is not None else template.supports_reasoning,
                        supports_vision=f_spec.supports_vision if f_spec.supports_vision is not None else template.supports_vision,
                        tier="economy" if "mini" in f_spec.name or "flash" in f_spec.name or "haiku" in f_spec.name else "balanced",
                        active=True,
                        enabled=True,
                        created_at=now,
                    )
                    db.add(new_model)
                    models_created_count += 1
            continue

        # Provider does not exist for this org: create it from template
        env_var_name = _ENV_VARS.get(template.key, "")
        env_api_key = os.environ.get(env_var_name, "").strip() if env_var_name else ""
        if template.key == "gemini" and not env_api_key:
            env_api_key = os.environ.get("GEMINI_API_KEY", "").strip()

        is_default = False
        if not has_default and (template.key == "openai" or created_count == 0):
            is_default = True
            has_default = True

        provider_id = gen_id()
        encrypted_key = encrypt_string(env_api_key) if env_api_key else None
        last4 = env_api_key[-4:] if env_api_key else None

        new_provider = Provider(
            id=provider_id,
            org_id=org_id,
            created_by_user_id=None,
            key=template.key,
            name=template.display_name,
            base_url=template.default_base_url,
            normalized_base_url=template.default_base_url.strip().rstrip("/").lower(),
            template_key=template.key,
            api_key="",
            api_key_encrypted=encrypted_key,
            api_key_last4=last4,
            env_var=env_var_name,
            is_default=is_default,
            status="ready",
            discovery_status="ready",
            models_discovered=len(template.fallback_models),
            created_at=now,
            updated_at=now,
        )
        db.add(new_provider)
        await db.flush()
        created_count += 1

        # Populate fallback models
        for f_spec in template.fallback_models:
            model = Model(
                id=gen_id(),
                org_id=org_id,
                provider_id=new_provider.id,
                name=f_spec.name,
                display_name=f_spec.display_name,
                context_window=f_spec.context_window,
                input_cost_per_1k=f_spec.input_cost_per_1k,
                output_cost_per_1k=f_spec.output_cost_per_1k,
                supports_tools=f_spec.supports_tools if f_spec.supports_tools is not None else template.supports_tools,
                supports_reasoning=f_spec.supports_reasoning if f_spec.supports_reasoning is not None else template.supports_reasoning,
                supports_vision=f_spec.supports_vision if f_spec.supports_vision is not None else template.supports_vision,
                tier="economy" if "mini" in f_spec.name or "flash" in f_spec.name or "haiku" in f_spec.name else "balanced",
                active=True,
                enabled=True,
                created_at=now,
            )
            db.add(model)
            models_created_count += 1

    await db.flush()
    return SystemProviderSyncResult(
        org_id=org_id,
        created=created_count,
        skipped=skipped_count,
        models_created=models_created_count,
    )


async def sync_system_providers_all_orgs(db: AsyncSession) -> list[SystemProviderSyncResult]:
    """Sync provider templates for every active organization without clobbering existing customizations."""
    org_ids = (
        await db.scalars(
            select(Organization.id).where(Organization.lifecycle_status != "deleted")
        )
    ).all()
    results: list[SystemProviderSyncResult] = []
    for org_id in org_ids:
        res = await sync_system_providers_for_org(db, org_id)
        results.append(res)
        if res.created or res.models_created:
            await logger.ainfo(
                "system_providers_synced",
                org_id=org_id,
                created=res.created,
                skipped=res.skipped,
                models_created=res.models_created,
            )
    await db.commit()
    return results
