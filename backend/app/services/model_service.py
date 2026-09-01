from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select

from app.db.base import utc_now
from app.models.model import Model
from app.models.org_model_tier_config import OrgModelTierConfig
from app.repositories.model_repo import ModelRepository
from app.repositories.provider_repo import ProviderRepository

GRACE_PERIOD = timedelta(days=7)


class ModelService:
    def __init__(self, db):
        self.repo = ModelRepository(db)
        self.provider_repo = ProviderRepository(db)
        self.db = db

    @staticmethod
    def recompute_active(model: Model, now=None) -> bool:
        now = now or utc_now()
        if not model.enabled:
            model.active = False
        elif model.source != "discovered" or model.last_seen_at is None:
            model.active = True
        else:
            model.active = now - model.last_seen_at <= GRACE_PERIOD
        return model.active

    async def create(self, org_id: str, data: dict, user_id: str | None = None) -> Model:
        prov = await self.provider_repo.get(org_id, data["provider_id"])
        if prov is None:
            raise ValueError("provider not found")
        data = dict(data)
        enabled = data.pop("enabled", None)
        if enabled is None:
            enabled = bool(data.get("active", True))
        data["active"] = bool(enabled)
        data["enabled"] = bool(enabled)
        data.setdefault("source", "manual")
        data["org_id"] = org_id
        if user_id:
            data["created_by_user_id"] = user_id
        return await self.repo.create(Model(**data))

    async def update(self, org_id: str, id: str, data: dict) -> Model:
        m = await self.repo.get(org_id, id)
        if m is None:
            raise ValueError("model not found")
        data = dict(data)
        if "enabled" in data:
            m.enabled = bool(data.pop("enabled"))
        elif "active" in data:
            # Backward-compatible callers used active as the toggle.
            m.enabled = bool(data.pop("active"))
        for key, value in data.items():
            if hasattr(m, key):
                setattr(m, key, value)
        self.recompute_active(m)
        await self.db.commit()
        await self.db.refresh(m)
        return m

    async def delete(self, org_id: str, id: str) -> bool:
        return await self.repo.delete(org_id, id)

    async def list(
        self,
        org_id: str,
        *,
        with_inactive: bool = False,
        active: bool | None = None,
        query: str | None = None,
        provider_id: str | None = None,
    ) -> list[Model]:
        rows = await self.repo.list_all(org_id, query=query, provider_id=provider_id)
        changed = False
        for row in rows:
            old_active = row.active
            expected = self.recompute_active(row)
            if old_active != expected:
                changed = True
        if changed:
            await self.db.commit()
        if active is not None:
            rows = [row for row in rows if row.active is active]
        elif not with_inactive:
            rows = [row for row in rows if row.active]
        return rows

    async def get(self, org_id: str, id: str) -> Model | None:
        return await self.repo.get(org_id, id)

    async def test_chat(self, org_id: str, id: str) -> dict:
        import time

        from app.core.providers.factory import build_driver
        from app.schemas.model import ModelTestResult

        model = await self.repo.get(org_id, id)
        if model is None:
            raise ValueError("model not found")

        prov = await self.provider_repo.get(org_id, model.provider_id)
        if prov is None:
            raise ValueError("provider not found")

        try:
            driver = build_driver(prov, model)
        except Exception as exc:
            return ModelTestResult(
                ok=False,
                latency_ms=0,
                message=f"Failed to initialize driver: {exc}",
                model_name=model.name,
            ).model_dump()

        test_messages = [{"role": "user", "content": "Hi, are you ready? Reply 'OK'."}]
        started_at = time.monotonic()
        try:
            content, _usage, _tool_calls = await driver.complete(
                test_messages,
                temperature=0.0,
            )
            elapsed_ms = max(1, int((time.monotonic() - started_at) * 1000))
            text_response = (content or "").strip()
            return ModelTestResult(
                ok=True,
                latency_ms=elapsed_ms,
                message="Model is responding successfully",
                sample_response=text_response[:100] if text_response else "OK",
                model_name=model.name,
            ).model_dump()
        except Exception as exc:
            elapsed_ms = max(1, int((time.monotonic() - started_at) * 1000))
            return ModelTestResult(
                ok=False,
                latency_ms=elapsed_ms,
                message=str(exc),
                model_name=model.name,
            ).model_dump()

    async def get_tier_matrix(self, org_id: str) -> dict[str, Model | None]:
        """Fetch the current 3-tier model matrix for the organization."""
        # 1. Fetch existing tier mappings
        res = await self.db.execute(
            select(OrgModelTierConfig).where(OrgModelTierConfig.org_id == org_id)
        )
        saved_configs = {cfg.tier: cfg for cfg in res.scalars().all()}

        # 2. Preload active models
        active_models = await self.list(org_id, active=True)
        active_by_id = {m.id: m for m in active_models}

        # 3. Resolve each tier: economy, balanced, frontier
        tiers: list[str] = ["economy", "balanced", "frontier"]
        result: dict[str, Model | None] = {}

        for tier in tiers:
            # Check explicit config first
            cfg = saved_configs.get(tier)
            if cfg and cfg.model_id and cfg.model_id in active_by_id:
                result[tier] = active_by_id[cfg.model_id]
                continue

            # Fallback 1: active model matching tier name
            matching = [m for m in active_models if getattr(m, "tier", None) == tier]
            if matching:
                result[tier] = matching[0]
                continue

            # Fallback 2: first available active model
            result[tier] = active_models[0] if active_models else None

        return result

    async def set_tier_matrix(
        self, org_id: str, tier_mappings: dict[str, str | None]
    ) -> dict[str, Model | None]:
        """Update or create tier mappings for the organization."""
        valid_tiers = {"economy", "balanced", "frontier"}
        for tier, model_id in tier_mappings.items():
            if tier not in valid_tiers:
                continue

            # Validate model belongs to org and is active if provided
            if model_id is not None:
                m = await self.repo.get(org_id, model_id)
                if m is None:
                    raise ValueError(f"Model {model_id} not found in organization")

            cfg = await self.db.scalar(
                select(OrgModelTierConfig).where(
                    OrgModelTierConfig.org_id == org_id,
                    OrgModelTierConfig.tier == tier,
                )
            )
            if cfg is None:
                cfg = OrgModelTierConfig(org_id=org_id, tier=tier, model_id=model_id)
                self.db.add(cfg)
            else:
                cfg.model_id = model_id

        await self.db.commit()
        return await self.get_tier_matrix(org_id)

