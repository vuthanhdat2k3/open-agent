from __future__ import annotations

import json
from typing import Any

from sqlalchemy import or_, select

from app.core.providers.templates import get_templates
from app.core.tools.registry import register
from app.core.tools.risk_tier import RiskTier
from app.core.tools.types import ToolContext, ToolSpec
from app.models.model import Model
from app.models.provider import Provider
from app.services.model_service import ModelService
from app.services.provider_service import ProviderService
from app.services.quota_service import QuotaService


async def _resolve_provider(db, org_id: str, provider_id_or_key: str) -> Provider | None:
    """Find a provider by ID or by key within the organization."""
    stmt = select(Provider).where(
        Provider.org_id == org_id,
        or_(
            Provider.id == provider_id_or_key,
            Provider.key == provider_id_or_key,
        ),
    )
    res = await db.execute(stmt)
    return res.scalars().first()


async def _resolve_model(db, org_id: str, model_id_or_name: str) -> Model | None:
    """Find a model by ID or name slug within the organization."""
    stmt = select(Model).where(
        Model.org_id == org_id,
        or_(
            Model.id == model_id_or_name,
            Model.name == model_id_or_name,
        ),
    )
    res = await db.execute(stmt)
    return res.scalars().first()


# ---------------------------------------------------------------------------
# 1. system_list_provider_templates
# ---------------------------------------------------------------------------
async def _system_list_provider_templates(args: dict[str, Any], ctx: ToolContext) -> str:
    templates = get_templates()
    items = []
    for t in templates:
        items.append({
            "key": t.key,
            "display_name": t.display_name,
            "description": t.description,
            "driver": t.driver,
            "default_base_url": t.default_base_url,
            "api_key_required": t.api_key_required,
            "supports_tools": t.supports_tools,
            "supports_reasoning": t.supports_reasoning,
            "supports_vision": t.supports_vision,
            "fallback_models": [
                {
                    "name": m.name,
                    "display_name": m.display_name,
                    "context_window": m.context_window,
                }
                for m in t.fallback_models
            ],
        })
    return json.dumps({"count": len(items), "templates": items}, ensure_ascii=False, indent=2)


register(
    ToolSpec(
        name="system_list_provider_templates",
        description="List all supported built-in AI provider templates (e.g. OpenAI, OpenRouter, Anthropic, Gemini, DeepSeek, Ollama) and their capabilities.",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        risk_tier=RiskTier.safe,
        run=_system_list_provider_templates,
    )
)


# ---------------------------------------------------------------------------
# 2. system_list_providers
# ---------------------------------------------------------------------------
async def _system_list_providers(args: dict[str, Any], ctx: ToolContext) -> str:
    include_inactive = bool(args.get("include_inactive", True))
    providers = await ProviderService(ctx.db).list(ctx.org_id)
    if not include_inactive:
        providers = [p for p in providers if p.status == "ready"]

    # Pre-fetch model counts
    model_counts: dict[str, int] = {}
    m_stmt = select(Model.provider_id).where(Model.org_id == ctx.org_id)
    m_res = await ctx.db.execute(m_stmt)
    for p_id in m_res.scalars().all():
        model_counts[p_id] = model_counts.get(p_id, 0) + 1

    items = []
    for p in providers:
        items.append({
            "id": p.id,
            "key": p.key,
            "name": p.name,
            "base_url": p.base_url,
            "template_key": p.template_key,
            "is_default": p.is_default,
            "status": p.status,
            "discovery_status": p.discovery_status,
            "models_count": model_counts.get(p.id, 0),
            "api_key_configured": p.api_key_configured,
            "api_key_last4": p.api_key_last4,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        })

    return json.dumps({"count": len(items), "providers": items}, ensure_ascii=False, indent=2)


register(
    ToolSpec(
        name="system_list_providers",
        description="List all configured AI providers in the organization, including their status, model counts, and whether credentials are configured.",
        input_schema={
            "type": "object",
            "properties": {
                "include_inactive": {
                    "type": "boolean",
                    "description": "Whether to include inactive or error status providers (default: True)",
                }
            },
            "additionalProperties": False,
        },
        risk_tier=RiskTier.safe,
        run=_system_list_providers,
    )
)


# ---------------------------------------------------------------------------
# 3. system_get_provider
# ---------------------------------------------------------------------------
async def _system_get_provider(args: dict[str, Any], ctx: ToolContext) -> str:
    provider_id = (args.get("provider_id") or "").strip()
    if not provider_id:
        return json.dumps({"error": "provider_id is required"})

    prov = await _resolve_provider(ctx.db, ctx.org_id, provider_id)
    if prov is None:
        return json.dumps({"error": f"Provider '{provider_id}' not found in organization."})

    # Fetch associated models
    m_stmt = select(Model).where(Model.org_id == ctx.org_id, Model.provider_id == prov.id)
    m_res = await ctx.db.execute(m_stmt)
    models = m_res.scalars().all()

    model_items = [
        {
            "id": m.id,
            "name": m.name,
            "display_name": m.display_name,
            "tier": m.tier,
            "active": m.active,
            "enabled": m.enabled,
            "context_window": m.context_window,
            "supports_tools": m.supports_tools,
            "supports_reasoning": m.supports_reasoning,
            "supports_vision": m.supports_vision,
        }
        for m in models
    ]

    return json.dumps({
        "provider": {
            "id": prov.id,
            "key": prov.key,
            "name": prov.name,
            "base_url": prov.base_url,
            "template_key": prov.template_key,
            "is_default": prov.is_default,
            "status": prov.status,
            "discovery_status": prov.discovery_status,
            "discovery_error": prov.discovery_error,
            "api_key_configured": bool(prov.api_key_last4 or prov.api_key_encrypted),
            "api_key_last4": prov.api_key_last4,
            "created_at": prov.created_at.isoformat() if prov.created_at else None,
            "models_count": len(model_items),
            "models": model_items,
        }
    }, ensure_ascii=False, indent=2)


register(
    ToolSpec(
        name="system_get_provider",
        description="Get detailed settings and associated models for a specific AI provider by ID or key.",
        input_schema={
            "type": "object",
            "properties": {
                "provider_id": {"type": "string", "description": "The provider ID or key"}
            },
            "required": ["provider_id"],
            "additionalProperties": False,
        },
        risk_tier=RiskTier.safe,
        run=_system_get_provider,
    )
)


# ---------------------------------------------------------------------------
# 4. system_create_provider
# ---------------------------------------------------------------------------
async def _system_create_provider(args: dict[str, Any], ctx: ToolContext) -> str:
    template_key = (args.get("template_key") or "").strip().lower()
    name = (args.get("name") or "").strip()
    api_key = (args.get("api_key") or "").strip()
    base_url = (args.get("base_url") or "").strip() or None
    is_default = bool(args.get("is_default", False))

    if not template_key:
        return json.dumps({"error": "template_key is required (e.g. 'openai', 'openrouter', 'anthropic', 'gemini', 'deepseek', 'ollama', or 'custom')"})

    known_templates = {t.key: t for t in get_templates()}
    service = ProviderService(ctx.db)

    try:
        if template_key in known_templates:
            prov = await service.create_from_template(
                ctx.org_id,
                template_key=template_key,
                api_key=api_key,
                base_url=base_url,
                is_default=is_default,
                user_id=ctx.user_id,
            )
            if name and name != prov.name:
                prov = await service.update(ctx.org_id, prov.id, {"name": name})
        else:
            # Custom provider
            data = {
                "key": template_key if template_key != "custom" else f"custom-{name.lower().replace(' ', '-')[:20]}",
                "name": name or template_key,
                "base_url": base_url or "https://api.openai.com/v1",
                "api_key": api_key,
                "is_default": is_default,
            }
            prov = await service.create(ctx.org_id, data, user_id=ctx.user_id)

        return json.dumps({
            "message": f"Provider '{prov.name}' created successfully.",
            "provider": {
                "id": prov.id,
                "key": prov.key,
                "name": prov.name,
                "base_url": prov.base_url,
                "template_key": prov.template_key,
                "is_default": prov.is_default,
                "status": prov.status,
            }
        }, ensure_ascii=False, indent=2)
    except Exception as exc:
        return json.dumps({"error": f"Failed to create provider: {exc}"})


register(
    ToolSpec(
        name="system_create_provider",
        description="Add a new AI provider to the organization from a template (e.g., openai, openrouter, deepseek, gemini, anthropic, ollama) or custom endpoint.",
        input_schema={
            "type": "object",
            "properties": {
                "template_key": {
                    "type": "string",
                    "description": "Template key (openai, openrouter, deepseek, anthropic, gemini, ollama, or custom)",
                },
                "name": {"type": "string", "description": "Display name (optional, defaults to template name)"},
                "api_key": {"type": "string", "description": "API key secret"},
                "base_url": {"type": "string", "description": "API Base URL (optional override)"},
                "is_default": {"type": "boolean", "description": "Set as default provider (default: False)"},
            },
            "required": ["template_key"],
            "additionalProperties": False,
        },
        risk_tier=RiskTier.write,
        run=_system_create_provider,
    )
)


# ---------------------------------------------------------------------------
# 5. system_update_provider
# ---------------------------------------------------------------------------
async def _system_update_provider(args: dict[str, Any], ctx: ToolContext) -> str:
    provider_id = (args.get("provider_id") or "").strip()
    if not provider_id:
        return json.dumps({"error": "provider_id is required"})

    prov = await _resolve_provider(ctx.db, ctx.org_id, provider_id)
    if prov is None:
        return json.dumps({"error": f"Provider '{provider_id}' not found."})

    update_data: dict[str, Any] = {}
    if "name" in args and args["name"] is not None:
        update_data["name"] = str(args["name"]).strip()
    if "base_url" in args and args["base_url"] is not None:
        update_data["base_url"] = str(args["base_url"]).strip()
    if "api_key" in args and args["api_key"] is not None:
        update_data["api_key"] = str(args["api_key"]).strip()
    if "is_default" in args and args["is_default"] is not None:
        update_data["is_default"] = bool(args["is_default"])

    if not update_data:
        return json.dumps({"message": "No update fields provided."})

    try:
        updated = await ProviderService(ctx.db).update(ctx.org_id, prov.id, update_data)
        return json.dumps({
            "message": f"Provider '{updated.name}' updated successfully.",
            "provider": {
                "id": updated.id,
                "key": updated.key,
                "name": updated.name,
                "base_url": updated.base_url,
                "is_default": updated.is_default,
                "status": updated.status,
            }
        }, ensure_ascii=False, indent=2)
    except Exception as exc:
        return json.dumps({"error": f"Failed to update provider: {exc}"})


register(
    ToolSpec(
        name="system_update_provider",
        description="Update configuration, credentials, or default status of an existing AI provider.",
        input_schema={
            "type": "object",
            "properties": {
                "provider_id": {"type": "string", "description": "The provider ID or key"},
                "name": {"type": "string", "description": "New display name"},
                "base_url": {"type": "string", "description": "New API base URL"},
                "api_key": {"type": "string", "description": "New API key credential"},
                "is_default": {"type": "boolean", "description": "Whether this provider is the default"},
            },
            "required": ["provider_id"],
            "additionalProperties": False,
        },
        risk_tier=RiskTier.write,
        run=_system_update_provider,
    )
)


# ---------------------------------------------------------------------------
# 6. system_test_provider
# ---------------------------------------------------------------------------
async def _system_test_provider(args: dict[str, Any], ctx: ToolContext) -> str:
    provider_id = (args.get("provider_id") or "").strip()
    if not provider_id:
        return json.dumps({"error": "provider_id is required"})

    prov = await _resolve_provider(ctx.db, ctx.org_id, provider_id)
    if prov is None:
        return json.dumps({"error": f"Provider '{provider_id}' not found."})

    result = await ProviderService(ctx.db).test_connection(ctx.org_id, prov.id)
    return json.dumps({
        "provider_name": prov.name,
        "test_result": result,
    }, ensure_ascii=False, indent=2)


register(
    ToolSpec(
        name="system_test_provider",
        description="Test connection and trigger model discovery for a configured AI provider.",
        input_schema={
            "type": "object",
            "properties": {
                "provider_id": {"type": "string", "description": "The provider ID or key"}
            },
            "required": ["provider_id"],
            "additionalProperties": False,
        },
        risk_tier=RiskTier.network,
        run=_system_test_provider,
    )
)


# ---------------------------------------------------------------------------
# 7. system_list_models
# ---------------------------------------------------------------------------
async def _system_list_models(args: dict[str, Any], ctx: ToolContext) -> str:
    provider_id = (args.get("provider_id") or "").strip() or None
    enabled_only = bool(args.get("enabled_only", False))
    query = (args.get("query") or "").strip() or None

    resolved_provider_id = None
    if provider_id:
        prov = await _resolve_provider(ctx.db, ctx.org_id, provider_id)
        resolved_provider_id = prov.id if prov else provider_id

    service = ModelService(ctx.db)
    models = await service.list(
        ctx.org_id,
        with_inactive=not enabled_only,
        active=True if enabled_only else None,
        query=query,
        provider_id=resolved_provider_id,
    )

    items = []
    for m in models:
        items.append({
            "id": m.id,
            "name": m.name,
            "display_name": m.display_name,
            "provider_id": m.provider_id,
            "provider_name": getattr(m.provider, "name", None) if getattr(m, "provider", None) else None,
            "tier": m.tier,
            "active": m.active,
            "enabled": m.enabled,
            "context_window": m.context_window,
            "input_cost_per_1k": m.input_cost_per_1k,
            "output_cost_per_1k": m.output_cost_per_1k,
            "supports_tools": m.supports_tools,
            "supports_reasoning": m.supports_reasoning,
            "supports_vision": m.supports_vision,
        })

    return json.dumps({
        "count": len(items),
        "models": items,
    }, ensure_ascii=False, indent=2)


register(
    ToolSpec(
        name="system_list_models",
        description="List AI models in the organization catalog, with filtering by provider, enabled status, or keyword search.",
        input_schema={
            "type": "object",
            "properties": {
                "provider_id": {"type": "string", "description": "Optional provider ID or key filter"},
                "enabled_only": {"type": "boolean", "description": "Only return enabled models (default: False)"},
                "query": {"type": "string", "description": "Search keyword in model name or display name"},
            },
            "additionalProperties": False,
        },
        risk_tier=RiskTier.safe,
        run=_system_list_models,
    )
)


# ---------------------------------------------------------------------------
# 8. system_get_model
# ---------------------------------------------------------------------------
async def _system_get_model(args: dict[str, Any], ctx: ToolContext) -> str:
    model_id = (args.get("model_id") or "").strip()
    if not model_id:
        return json.dumps({"error": "model_id is required"})

    m = await _resolve_model(ctx.db, ctx.org_id, model_id)
    if m is None:
        return json.dumps({"error": f"Model '{model_id}' not found."})

    return json.dumps({
        "model": {
            "id": m.id,
            "name": m.name,
            "display_name": m.display_name,
            "provider_id": m.provider_id,
            "tier": m.tier,
            "active": m.active,
            "enabled": m.enabled,
            "context_window": m.context_window,
            "input_cost_per_1k": m.input_cost_per_1k,
            "output_cost_per_1k": m.output_cost_per_1k,
            "supports_tools": m.supports_tools,
            "supports_reasoning": m.supports_reasoning,
            "supports_vision": m.supports_vision,
            "source": m.source,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
    }, ensure_ascii=False, indent=2)


register(
    ToolSpec(
        name="system_get_model",
        description="Get detailed specifications and status for a specific AI model by ID or name slug (e.g. 'gpt-4o-mini').",
        input_schema={
            "type": "object",
            "properties": {
                "model_id": {"type": "string", "description": "Model ID (UUID) or model name slug"}
            },
            "required": ["model_id"],
            "additionalProperties": False,
        },
        risk_tier=RiskTier.safe,
        run=_system_get_model,
    )
)


# ---------------------------------------------------------------------------
# 9. system_toggle_model
# ---------------------------------------------------------------------------
async def _system_toggle_model(args: dict[str, Any], ctx: ToolContext) -> str:
    model_id = (args.get("model_id") or "").strip()
    if not model_id:
        return json.dumps({"error": "model_id is required"})
    if "enabled" not in args:
        return json.dumps({"error": "enabled (boolean) is required"})
    enabled = bool(args["enabled"])

    m = await _resolve_model(ctx.db, ctx.org_id, model_id)
    if m is None:
        return json.dumps({"error": f"Model '{model_id}' not found."})

    updated = await ModelService(ctx.db).update(ctx.org_id, m.id, {"enabled": enabled})
    action_str = "enabled" if enabled else "disabled"
    return json.dumps({
        "message": f"Model '{updated.name}' ({updated.display_name}) has been {action_str}.",
        "model": {
            "id": updated.id,
            "name": updated.name,
            "display_name": updated.display_name,
            "enabled": updated.enabled,
            "active": updated.active,
        }
    }, ensure_ascii=False, indent=2)


register(
    ToolSpec(
        name="system_toggle_model",
        description="Enable or disable an AI model in the organization catalog.",
        input_schema={
            "type": "object",
            "properties": {
                "model_id": {"type": "string", "description": "Model ID (UUID) or model name slug"},
                "enabled": {"type": "boolean", "description": "True to enable, False to disable"},
            },
            "required": ["model_id", "enabled"],
            "additionalProperties": False,
        },
        risk_tier=RiskTier.write,
        run=_system_toggle_model,
    )
)


# ---------------------------------------------------------------------------
# 10. system_update_model
# ---------------------------------------------------------------------------
async def _system_update_model(args: dict[str, Any], ctx: ToolContext) -> str:
    model_id = (args.get("model_id") or "").strip()
    if not model_id:
        return json.dumps({"error": "model_id is required"})

    m = await _resolve_model(ctx.db, ctx.org_id, model_id)
    if m is None:
        return json.dumps({"error": f"Model '{model_id}' not found."})

    update_fields: dict[str, Any] = {}
    for key in (
        "display_name",
        "tier",
        "context_window",
        "input_cost_per_1k",
        "output_cost_per_1k",
        "supports_tools",
        "supports_reasoning",
        "supports_vision",
    ):
        if key in args and args[key] is not None:
            update_fields[key] = args[key]

    if not update_fields:
        return json.dumps({"message": "No update fields provided."})

    try:
        updated = await ModelService(ctx.db).update(ctx.org_id, m.id, update_fields)
        return json.dumps({
            "message": f"Model '{updated.name}' updated successfully.",
            "model": {
                "id": updated.id,
                "name": updated.name,
                "display_name": updated.display_name,
                "tier": updated.tier,
                "context_window": updated.context_window,
                "input_cost_per_1k": updated.input_cost_per_1k,
                "output_cost_per_1k": updated.output_cost_per_1k,
                "supports_tools": updated.supports_tools,
                "supports_reasoning": updated.supports_reasoning,
                "supports_vision": updated.supports_vision,
            }
        }, ensure_ascii=False, indent=2)
    except Exception as exc:
        return json.dumps({"error": f"Failed to update model: {exc}"})


register(
    ToolSpec(
        name="system_update_model",
        description="Update model metadata: display name, routing tier, context window token limit, pricing, and capability flags.",
        input_schema={
            "type": "object",
            "properties": {
                "model_id": {"type": "string", "description": "Model ID (UUID) or model name slug"},
                "display_name": {"type": "string", "description": "New display name"},
                "tier": {"type": "string", "enum": ["economy", "balanced", "frontier"], "description": "Model tier"},
                "context_window": {"type": "integer", "description": "Context window in tokens"},
                "input_cost_per_1k": {"type": "number", "description": "Input cost per 1k tokens in USD"},
                "output_cost_per_1k": {"type": "number", "description": "Output cost per 1k tokens in USD"},
                "supports_tools": {"type": "boolean", "description": "Whether model supports function calling"},
                "supports_reasoning": {"type": "boolean", "description": "Whether model supports reasoning"},
                "supports_vision": {"type": "boolean", "description": "Whether model supports vision/images"},
            },
            "required": ["model_id"],
            "additionalProperties": False,
        },
        risk_tier=RiskTier.write,
        run=_system_update_model,
    )
)


# ---------------------------------------------------------------------------
# 11. system_test_model
# ---------------------------------------------------------------------------
async def _system_test_model(args: dict[str, Any], ctx: ToolContext) -> str:
    model_id = (args.get("model_id") or "").strip()
    if not model_id:
        return json.dumps({"error": "model_id is required"})

    m = await _resolve_model(ctx.db, ctx.org_id, model_id)
    if m is None:
        return json.dumps({"error": f"Model '{model_id}' not found."})

    try:
        result = await ModelService(ctx.db).test_chat(ctx.org_id, m.id)
        return json.dumps({
            "model_name": m.name,
            "test_result": result,
        }, ensure_ascii=False, indent=2)
    except Exception as exc:
        return json.dumps({"error": f"Model test failed: {exc}"})


register(
    ToolSpec(
        name="system_test_model",
        description="Test chat completion connectivity and measure response latency for an AI model.",
        input_schema={
            "type": "object",
            "properties": {
                "model_id": {"type": "string", "description": "Model ID (UUID) or model name slug to test"}
            },
            "required": ["model_id"],
            "additionalProperties": False,
        },
        risk_tier=RiskTier.network,
        run=_system_test_model,
    )
)


# ---------------------------------------------------------------------------
# 12. system_get_model_tiers
# ---------------------------------------------------------------------------
async def _system_get_model_tiers(args: dict[str, Any], ctx: ToolContext) -> str:
    service = ModelService(ctx.db)
    tiers = await service.get_tier_matrix(ctx.org_id)

    formatted: dict[str, Any] = {}
    for tier_name, model in tiers.items():
        if model:
            formatted[tier_name] = {
                "model_id": model.id,
                "model_name": model.name,
                "display_name": model.display_name,
                "provider_id": model.provider_id,
                "context_window": model.context_window,
            }
        else:
            formatted[tier_name] = None

    return json.dumps({
        "tier_matrix": formatted,
        "description": {
            "economy": "Fast, inexpensive tier (used for simple tasks, summarization, quick filters)",
            "balanced": "Standard tier (default for general workflows and multi-turn conversations)",
            "frontier": "Reasoning & frontier tier (used for complex logic, deep research, coding)",
        }
    }, ensure_ascii=False, indent=2)


register(
    ToolSpec(
        name="system_get_model_tiers",
        description="Get the organization's 3-tier model routing matrix (economy, balanced, frontier).",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        risk_tier=RiskTier.safe,
        run=_system_get_model_tiers,
    )
)


# ---------------------------------------------------------------------------
# 13. system_set_model_tier
# ---------------------------------------------------------------------------
async def _system_set_model_tier(args: dict[str, Any], ctx: ToolContext) -> str:
    tier = (args.get("tier") or "").strip().lower()
    model_id = (args.get("model_id") or "").strip()

    if tier not in {"economy", "balanced", "frontier"}:
        return json.dumps({"error": "tier must be one of: 'economy', 'balanced', 'frontier'"})
    if not model_id:
        return json.dumps({"error": "model_id is required"})

    m = await _resolve_model(ctx.db, ctx.org_id, model_id)
    if m is None:
        return json.dumps({"error": f"Model '{model_id}' not found in organization."})

    try:
        service = ModelService(ctx.db)
        updated_matrix = await service.set_tier_matrix(ctx.org_id, {tier: m.id})
        res: dict[str, Any] = {}
        for t_name, mod in updated_matrix.items():
            res[t_name] = {
                "model_id": mod.id,
                "model_name": mod.name,
                "display_name": mod.display_name,
            } if mod else None

        return json.dumps({
            "message": f"Successfully mapped tier '{tier}' to model '{m.name}' ({m.display_name}).",
            "tier_matrix": res,
        }, ensure_ascii=False, indent=2)
    except Exception as exc:
        return json.dumps({"error": f"Failed to set model tier: {exc}"})


register(
    ToolSpec(
        name="system_set_model_tier",
        description="Set which model should serve a specific system routing tier (economy, balanced, or frontier).",
        input_schema={
            "type": "object",
            "properties": {
                "tier": {
                    "type": "string",
                    "enum": ["economy", "balanced", "frontier"],
                    "description": "Routing tier",
                },
                "model_id": {"type": "string", "description": "Model ID (UUID) or model name slug"},
            },
            "required": ["tier", "model_id"],
            "additionalProperties": False,
        },
        risk_tier=RiskTier.write,
        run=_system_set_model_tier,
    )
)


# ---------------------------------------------------------------------------
# 14. system_get_quotas
# ---------------------------------------------------------------------------
async def _system_get_quotas(args: dict[str, Any], ctx: ToolContext) -> str:
    quota_service = QuotaService(ctx.db)
    quota = await quota_service.get(ctx.org_id)
    if quota is None:
        return json.dumps({"error": "Organization quota not found."})

    try:
        usage = await quota_service.usage(ctx.org_id)
    except Exception:
        usage = None

    result: dict[str, Any] = {
        "limits": {
            "monthly_cost_usd": quota.monthly_cost_usd,
            "requests_per_minute": quota.requests_per_minute,
            "agent_runs_per_minute": quota.agent_runs_per_minute,
            "max_concurrent_runs": quota.max_concurrent_runs,
            "max_agents": quota.max_agents,
            "max_workflows": quota.max_workflows,
            "max_storage_bytes": quota.max_storage_bytes,
            "enforcement_mode": quota.enforcement_mode,
        }
    }
    if usage:
        result["current_usage"] = usage

    return json.dumps(result, ensure_ascii=False, indent=2)


register(
    ToolSpec(
        name="system_get_quotas",
        description="Inspect organization quota limits (monthly cost budget, rate limits) and current real-time usage.",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        risk_tier=RiskTier.safe,
        run=_system_get_quotas,
    )
)


# ---------------------------------------------------------------------------
# 15. system_set_quota
# ---------------------------------------------------------------------------
async def _system_set_quota(args: dict[str, Any], ctx: ToolContext) -> str:
    update_data: dict[str, Any] = {}
    for key in (
        "monthly_cost_usd",
        "requests_per_minute",
        "agent_runs_per_minute",
        "max_concurrent_runs",
        "max_agents",
        "max_workflows",
        "max_storage_bytes",
        "enforcement_mode",
    ):
        if key in args and args[key] is not None:
            update_data[key] = args[key]

    if not update_data:
        return json.dumps({"message": "No quota fields provided to update."})

    try:
        quota_service = QuotaService(ctx.db)
        updated = await quota_service.update(ctx.org_id, update_data, user_id=ctx.user_id)
        return json.dumps({
            "message": "Organization quota updated successfully.",
            "limits": {
                "monthly_cost_usd": updated.monthly_cost_usd,
                "requests_per_minute": updated.requests_per_minute,
                "agent_runs_per_minute": updated.agent_runs_per_minute,
                "max_concurrent_runs": updated.max_concurrent_runs,
                "max_agents": updated.max_agents,
                "max_workflows": updated.max_workflows,
                "max_storage_bytes": updated.max_storage_bytes,
                "enforcement_mode": updated.enforcement_mode,
            }
        }, ensure_ascii=False, indent=2)
    except Exception as exc:
        return json.dumps({"error": f"Failed to update quota: {exc}"})


register(
    ToolSpec(
        name="system_set_quota",
        description="Update organization quota limits such as monthly cost limit, rate limits, or enforcement mode.",
        input_schema={
            "type": "object",
            "properties": {
                "monthly_cost_usd": {"type": "number", "description": "Monthly spend limit in USD"},
                "requests_per_minute": {"type": "integer", "description": "Max requests per minute"},
                "agent_runs_per_minute": {"type": "integer", "description": "Max agent runs per minute"},
                "max_concurrent_runs": {"type": "integer", "description": "Max concurrent runs"},
                "max_agents": {"type": "integer", "description": "Max custom agents allowed"},
                "max_workflows": {"type": "integer", "description": "Max workflows allowed"},
                "max_storage_bytes": {"type": "integer", "description": "Max storage allowed in bytes"},
                "enforcement_mode": {"type": "string", "enum": ["enforce", "observe"], "description": "Enforcement mode"},
            },
            "additionalProperties": False,
        },
        risk_tier=RiskTier.write,
        run=_system_set_quota,
    )
)
