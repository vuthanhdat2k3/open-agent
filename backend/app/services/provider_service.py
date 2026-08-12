from __future__ import annotations

import structlog
from sqlalchemy import select

from app.core.credential_secrets import encrypt_string
from app.core.providers.factory import build_driver
from app.core.providers.templates import ProviderTemplate, get_template
from app.core.workflow.queue import enqueue_provider_discovery
from app.db.base import utc_now
from app.models.model import Model
from app.models.provider import Provider
from app.repositories.provider_repo import ProviderRepository
from app.schemas.provider import ProviderTestResult
from app.services.model_discovery_service import ModelDiscoveryService
from app.services.model_service import ModelService

_ENV_VARS = {
    "openai": "OPENAI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "ollama": "OLLAMA_API_KEY",
    "gemini": "GOOGLE_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "opencode": "OPENCODE_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
}

logger = structlog.get_logger(__name__)


def normalize_base_url(url: str) -> str:
    return url.strip().rstrip("/").lower()


def _encrypted_key(value: str) -> tuple[str, str | None, str | None]:
    clean = value.strip()
    return "", (encrypt_string(clean) if clean else None), (clean[-4:] if clean else None)


class ProviderService:
    def __init__(self, db):
        self.repo = ProviderRepository(db)
        self.db = db

    async def create(self, org_id: str, data: dict, user_id: str | None = None) -> Provider:
        data = dict(data)
        raw_key = data.pop("api_key", "") or ""
        plain, encrypted, last4 = _encrypted_key(raw_key)
        data["api_key"] = plain
        data["api_key_encrypted"] = encrypted
        data["api_key_last4"] = last4
        data["normalized_base_url"] = normalize_base_url(data["base_url"])
        if data.get("is_default"):
            existing = await self.repo.get_default(org_id)
            if existing:
                existing.is_default = False
                self.db.add(existing)
        data["org_id"] = org_id
        if user_id:
            data["created_by_user_id"] = user_id
        prov = Provider(**data)
        return await self.repo.create(prov)

    async def update(self, org_id: str, id: str, data: dict) -> Provider:
        prov = await self.repo.get(org_id, id)
        if prov is None:
            raise ValueError("provider not found")
        data = dict(data)
        clear_key = bool(data.pop("clear_api_key", False))
        raw_key = data.pop("api_key", None)
        discovery_requested = clear_key or bool(raw_key)
        old_base_url = prov.normalized_base_url or normalize_base_url(prov.base_url)
        if clear_key:
            prov.api_key = ""
            prov.api_key_encrypted = None
            prov.api_key_last4 = None
        elif raw_key:
            prov.api_key, prov.api_key_encrypted, prov.api_key_last4 = _encrypted_key(raw_key)
        else:
            data.pop("api_key", None)
        if data.get("is_default"):
            existing = await self.repo.get_default(org_id)
            if existing and existing.id != id:
                existing.is_default = False
                self.db.add(existing)
        if "base_url" in data and data["base_url"]:
            data["normalized_base_url"] = normalize_base_url(data["base_url"])
            discovery_requested = discovery_requested or data["normalized_base_url"] != old_base_url
        if discovery_requested:
            prov.discovery_generation = (prov.discovery_generation or 0) + 1
            prov.discovery_status = "pending"
            prov.discovery_error = None
        updated = await self.repo.update(prov, data)
        if discovery_requested:
            try:
                await enqueue_provider_discovery(
                    updated.id, updated.discovery_generation
                )
            except Exception as exc:  # noqa: BLE001 - reconcile pending state later.
                await logger.awarning(
                    "provider_discovery_enqueue_failed",
                    provider_id=updated.id,
                    discovery_generation=updated.discovery_generation,
                    error_type=type(exc).__name__,
                )
        return updated

    async def delete(self, org_id: str, id: str) -> bool:
        return await self.repo.delete(org_id, id)

    async def list(self, org_id: str) -> list[Provider]:
        return await self.repo.list_all(org_id)

    async def get(self, org_id: str, id: str) -> Provider | None:
        return await self.repo.get(org_id, id)

    @staticmethod
    def _driver_for(provider: Provider, model_name: str = ""):
        return build_driver(provider, Model(name=model_name or "discovery"))

    async def _persist_discovery(
        self,
        provider: Provider,
        template: ProviderTemplate | None,
        result,
        *,
        now,
    ) -> int:
        discovered_count = len(result.models) if result.discovery_success else 0
        provider.last_discovery_attempt_at = result.attempted_at or now
        provider.discovery_error = result.discovery_error
        provider.discovery_status = "complete" if result.discovery_success else "failed"
        provider.models_discovered = discovered_count
        provider.status = "ready" if result.test.ok else "error"
        if result.discovery_success:
            provider.last_successful_discovery_at = result.attempted_at or now

        if not result.test.ok:
            return 0
        existing_result = await self.db.execute(
            select(Model).where(Model.org_id == provider.org_id, Model.provider_id == provider.id)
        )
        existing_by_name = {row.name: row for row in existing_result.scalars().all()}
        source = "discovered" if result.discovery_success else "fallback"
        for info in result.models:
            row = existing_by_name.get(info.name)
            if row is None:
                values = ModelDiscoveryService.model_values(
                    info, source=source, template=template or _legacy_template(), now=now
                )
                row = Model(
                    org_id=provider.org_id,
                    provider_id=provider.id,
                    enabled=False,
                    active=False,
                    **values,
                )
                self.db.add(row)
                existing_by_name[info.name] = row
                continue
            if result.discovery_success or row.source == "fallback":
                row.display_name = info.display_name or row.display_name
                if info.context_window:
                    row.context_window = info.context_window
                if info.input_cost_per_1k is not None:
                    row.input_cost_per_1k = info.input_cost_per_1k
                if info.output_cost_per_1k is not None:
                    row.output_cost_per_1k = info.output_cost_per_1k
                row.last_discovered_at = now
                row.supports_tools = info.supports_tools
                row.supports_reasoning = info.supports_reasoning
                row.supports_vision = info.supports_vision
                if result.discovery_success:
                    row.discovered = True
                    row.source = "discovered"
                    row.last_seen_at = now
                    row.catalog_source = None
                    row.catalog_version = None
            if result.discovery_success:
                row.discovered = True

        # Recompute `active` for every model of this provider on every
        # discovery attempt (success or failure) so a model that has fallen
        # outside the grace period is deactivated even when this particular
        # run didn't mention it, without ever touching `enabled` directly.
        for row in existing_by_name.values():
            ModelService.recompute_active(row, now)
        return discovered_count

    async def create_from_template(
        self,
        org_id: str,
        template_key: str,
        api_key: str,
        base_url: str | None = None,
        is_default: bool = False,
        user_id: str | None = None,
    ) -> Provider:
        template = get_template(template_key)
        if template is None:
            raise ValueError("unknown provider template")
        if template.api_key_required and not api_key.strip():
            raise ValueError(f"{template.display_name} requires an API key")
        url = base_url.strip() if base_url and base_url.strip() else template.default_base_url
        normalized = normalize_base_url(url)
        probe_provider = Provider(
            key=template.key,
            name=template.display_name,
            base_url=url,
            normalized_base_url=normalized,
            template_key=template.key,
            api_key=api_key.strip(),
        )
        driver = self._driver_for(probe_provider, template.fallback_models[0].name if template.fallback_models else "discovery")
        result = await ModelDiscoveryService.probe(driver, template)
        if not result.test.ok:
            raise ValueError(result.test.message)

        await self.db.rollback()
        now = utc_now()
        async with self.db.begin():
            existing_result = await self.db.execute(
                select(Provider).where(
                    Provider.org_id == org_id,
                    Provider.template_key == template.key,
                    Provider.normalized_base_url == normalized,
                )
            )
            provider = existing_result.scalar_one_or_none()
            if provider is None:
                # Adopt a matching legacy seed row instead of colliding on its
                # org/key or org/name unique constraints.
                legacy_result = await self.db.execute(
                    select(Provider).where(
                        Provider.org_id == org_id,
                        Provider.key == template.key,
                        Provider.template_key.is_(None),
                    )
                )
                legacy = legacy_result.scalar_one_or_none()
                if legacy and normalize_base_url(legacy.base_url) == normalized:
                    provider = legacy
            plain, encrypted, last4 = _encrypted_key(api_key)
            if provider is None:
                provider = Provider(
                    org_id=org_id,
                    created_by_user_id=user_id,
                    key=template.key,
                    name=template.display_name,
                    base_url=url,
                    normalized_base_url=normalized,
                    template_key=template.key,
                    api_key=plain,
                    api_key_encrypted=encrypted,
                    api_key_last4=last4,
                    env_var=_ENV_VARS[template.key],
                    is_default=False,
                )
                self.db.add(provider)
                await self.db.flush()
            else:
                provider.base_url = url
                provider.normalized_base_url = normalized
                provider.template_key = template.key
                provider.key = template.key
                provider.name = template.display_name
                provider.api_key = plain
                provider.api_key_encrypted = encrypted
                provider.api_key_last4 = last4
                provider.env_var = _ENV_VARS[template.key]
            if is_default:
                defaults = await self.repo.get_default(org_id)
                if defaults and defaults.id != provider.id:
                    defaults.is_default = False
                provider.is_default = True
            await self._persist_discovery(provider, template, result, now=now)
            provider.status = "ready"
        await self.db.refresh(provider)
        return provider

    async def test_connection(self, org_id: str, id: str) -> dict:
        provider = await self.repo.get(org_id, id)
        if provider is None:
            return {"ok": False, "message": "provider not found", "latency_ms": 0, "model_count": 0}
        # End the read transaction before any network call. expire_on_commit is
        # false for the app session, so the ORM object remains usable.
        await self.db.commit()
        try:
            driver = self._driver_for(provider)
        except RuntimeError as exc:
            provider.status = "error"
            provider.discovery_status = "failed"
            provider.discovery_error = str(exc)
            await self.db.commit()
            return ProviderTestResult(ok=False, latency_ms=0, model_count=0, message=str(exc), status="error", discovery_status="failed", discovery_error=str(exc)).model_dump()
        template = get_template(provider.template_key or "")
        result = await ModelDiscoveryService.probe(driver, template or _legacy_template())
        async with self.db.begin():
            count = await self._persist_discovery(provider, template, result, now=utc_now())
        return ProviderTestResult(
            ok=result.test.ok,
            latency_ms=result.test.latency_ms,
            model_count=count,
            message="connected" if result.test.ok else result.test.message,
            status=provider.status,
            discovery_status=provider.discovery_status,
            discovery_error=provider.discovery_error,
            models_discovered=provider.models_discovered,
        ).model_dump()


def _legacy_template() -> ProviderTemplate:
    from app.core.providers.templates import FallbackModelSpec

    return ProviderTemplate(
        key="legacy",
        display_name="Custom provider",
        description="Legacy OpenAI-compatible provider",
        driver="openai_compatible",
        default_base_url="",
        api_key_required=False,
        supports_tools=True,
        supports_reasoning=False,
        supports_vision=False,
        catalog_source="legacy-fallback-v1",
        catalog_version="1",
        fallback_models=(FallbackModelSpec("custom-model", "Custom model"),),
    )
