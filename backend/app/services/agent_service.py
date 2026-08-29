from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, select

from app.core.agents.templates import SYSTEM_AGENT_BLUEPRINTS, SystemAgentBlueprint
from app.db.base import utc_now
from app.evals.quality_gate import quality_gate_passes
from app.models.agent import Agent
from app.models.agent_release import AgentRelease
from app.models.evaluation import EvaluationRun, EvaluationSuite
from app.models.model import Model
from app.models.org_agent_settings import OrgAgentSettings
from app.repositories.agent_repo import AgentRepository
from app.repositories.model_repo import ModelRepository

RELEASE_CONFIG_FIELDS = (
    "description",
    "system_prompt",
    "model_id",
    "tools",
    "allowed_risk_tiers",
    "kind",
    "max_iterations",
    "temperature",
)


class QualityGateBlocked(ValueError):
    """Publishing was refused because the release regressed on its suite.

    Distinct from other release errors so the API can answer 409 (a state
    conflict the caller may knowingly override) rather than 400 (a malformed
    request). Subclasses ValueError so existing handlers keep working.
    """

    def __init__(
        self, message: str, *, run_id: str, pass_rate: float, min_pass_rate: float
    ) -> None:
        super().__init__(message)
        self.run_id = run_id
        self.pass_rate = pass_rate
        self.min_pass_rate = min_pass_rate


@dataclass(frozen=True)
class RuntimeAgent:
    id: str
    org_id: str
    created_by_user_id: str | None
    name: str
    description: str
    system_prompt: str
    model_id: str
    tools: list[str]
    allowed_risk_tiers: list[str]
    kind: str
    max_iterations: int
    temperature: float
    active_release_id: str
    latest_release_number: int
    created_at: datetime
    updated_at: datetime
    enable_thinking: bool | None = None


def _snapshot(source: Agent | AgentRelease, overrides: dict | None = None) -> dict:
    values = {field: getattr(source, field) for field in RELEASE_CONFIG_FIELDS}
    values.update({k: v for k, v in (overrides or {}).items() if k in RELEASE_CONFIG_FIELDS and v is not None})
    return values


def _config_hash(config: dict) -> str:
    payload = json.dumps(config, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class AgentService:
    def __init__(self, db):
        self.repo = AgentRepository(db)
        self.model_repo = ModelRepository(db)

    async def create(self, org_id: str, data: dict, user_id: str | None = None) -> Agent:
        m = await self.model_repo.get(org_id, data["model_id"])
        if m is None or not m.active:
            raise ValueError("model not found or inactive")
        data["org_id"] = org_id
        if user_id:
            data["created_by_user_id"] = user_id
        if "allowed_risk_tiers" not in data or not data["allowed_risk_tiers"]:
            data["allowed_risk_tiers"] = ["safe", "read"]
        agent = Agent(**data)
        self.repo.db.add(agent)
        await self.repo.db.flush()
        release = AgentRelease(
            org_id=org_id,
            agent_id=agent.id,
            version=1,
            status="published",
            **_snapshot(agent),
            change_note="Initial release",
            config_hash=_config_hash(_snapshot(agent)),
            created_by_user_id=user_id,
            published_by_user_id=user_id,
            published_at=utc_now(),
        )
        self.repo.db.add(release)
        await self.repo.db.flush()
        agent.active_release_id = release.id
        agent.latest_release_number = 1
        await self.repo.db.commit()
        await self.repo.db.refresh(agent)
        return agent

    async def update(
        self, org_id: str, id: str, data: dict, user_id: str | None = None
    ) -> Agent:
        agent = await self._locked_agent(org_id, id)
        if agent is None:
            # Check if this is a System Blueprint being forked on write
            matched_blueprint = None
            for bp in SYSTEM_AGENT_BLUEPRINTS.values():
                if bp.id == id or bp.key == id or bp.name.lower() == id.lower():
                    matched_blueprint = bp
                    break
            if matched_blueprint is not None:
                # Check if an existing override exists by template_key
                existing_override = await self.repo.db.scalar(
                    select(Agent).where(
                        Agent.org_id == org_id,
                        Agent.template_key == matched_blueprint.key,
                    ).with_for_update()
                )
                if existing_override is not None:
                    agent = existing_override
                else:
                    resolved_model = await self._resolve_model_for_tier(org_id, matched_blueprint.recommended_tier)
                    model_to_use = data.get("model_id") or resolved_model
                    if not model_to_use:
                        raise ValueError("No active model found in organization to assign to agent")
                    base_data = {
                        "name": data.get("name") or matched_blueprint.name,
                        "description": data.get("description") if "description" in data else matched_blueprint.description,
                        "system_prompt": data.get("system_prompt") if "system_prompt" in data else matched_blueprint.system_prompt,
                        "model_id": model_to_use,
                        "tools": data.get("tools") if "tools" in data else list(matched_blueprint.tools),
                        "allowed_risk_tiers": data.get("allowed_risk_tiers") if "allowed_risk_tiers" in data else list(matched_blueprint.allowed_risk_tiers),
                        "kind": data.get("kind") or matched_blueprint.kind,
                        "max_iterations": data.get("max_iterations") if "max_iterations" in data else matched_blueprint.max_iterations,
                        "temperature": data.get("temperature") if "temperature" in data else matched_blueprint.temperature,
                        "enable_thinking": data.get("enable_thinking") if "enable_thinking" in data else matched_blueprint.enable_thinking,
                        "a2a_exposed": data.get("a2a_exposed") if "a2a_exposed" in data else matched_blueprint.a2a_exposed,
                        "auto_rollback_enabled": data.get("auto_rollback_enabled") if "auto_rollback_enabled" in data else matched_blueprint.auto_rollback_enabled,
                        "template_key": matched_blueprint.key,
                        "is_customized": True,
                    }
                    return await self.create(org_id, base_data, user_id)
            else:
                raise ValueError("agent not found")
        if "allowed_risk_tiers" in data and not data["allowed_risk_tiers"]:
            data.pop("allowed_risk_tiers")
        if "model_id" in data:
            await self._validate_model(org_id, data["model_id"])

        config_changes = {k: v for k, v in data.items() if k in RELEASE_CONFIG_FIELDS}
        for field in ("name", "a2a_exposed", "auto_rollback_enabled"):
            if field in data and data[field] is not None:
                setattr(agent, field, data[field])
        if "enable_thinking" in data:
            agent.enable_thinking = data["enable_thinking"]
        if config_changes:
            await self._create_release_locked(
                agent,
                config_changes,
                user_id=user_id,
                change_note="Updated through agent API",
                publish=True,
            )
        await self.repo.db.commit()
        await self.repo.db.refresh(agent)
        return agent

    async def list_releases(self, org_id: str, agent_id: str) -> list[AgentRelease]:
        if await self.repo.get(org_id, agent_id) is None:
            raise ValueError("agent not found")
        res = await self.repo.db.execute(
            select(AgentRelease)
            .where(AgentRelease.org_id == org_id, AgentRelease.agent_id == agent_id)
            .order_by(AgentRelease.version.desc())
        )
        return list(res.scalars().all())

    async def get_release(
        self, org_id: str, agent_id: str, version: int
    ) -> AgentRelease | None:
        res = await self.repo.db.execute(
            select(AgentRelease).where(
                AgentRelease.org_id == org_id,
                AgentRelease.agent_id == agent_id,
                AgentRelease.version == version,
            )
        )
        return res.scalar_one_or_none()

    async def create_release(
        self,
        org_id: str,
        agent_id: str,
        data: dict,
        user_id: str | None = None,
    ) -> AgentRelease:
        agent = await self._locked_agent(org_id, agent_id)
        if agent is None:
            raise ValueError("agent not found")
        if data.get("model_id"):
            await self._validate_model(org_id, data["model_id"])
        change_note = data.pop("change_note", "")
        release = await self._create_release_locked(
            agent,
            data,
            user_id=user_id,
            change_note=change_note,
            publish=False,
        )
        await self.repo.db.commit()
        await self.repo.db.refresh(release)
        return release

    async def publish_release(
        self,
        org_id: str,
        agent_id: str,
        version: int,
        user_id: str | None = None,
        force: bool = False,
    ) -> AgentRelease:
        agent = await self._locked_agent(org_id, agent_id)
        if agent is None:
            raise ValueError("agent not found")
        release = await self.get_release(org_id, agent_id, version)
        if release is None:
            raise ValueError("agent release not found")
        if agent.active_release_id == release.id:
            return release
        if release.status != "draft":
            raise ValueError("only a draft release can be published")
        # Check evaluation quality gate if evaluation runs exist for this release
        latest_run_res = await self.repo.db.execute(
            select(EvaluationRun)
            .where(
                EvaluationRun.org_id == org_id,
                EvaluationRun.agent_release_id == release.id,
                EvaluationRun.status == "completed",
            )
            .order_by(EvaluationRun.created_at.desc())
        )
        latest_run = latest_run_res.scalars().first()
        if latest_run is not None:
            suite_res = await self.repo.db.execute(
                select(EvaluationSuite).where(
                    EvaluationSuite.id == latest_run.suite_id,
                    EvaluationSuite.org_id == org_id,
                )
            )
            suite = suite_res.scalar_one_or_none()
            min_pass_rate = (
                suite.min_pass_rate
                if suite and hasattr(suite, "min_pass_rate")
                else 0.8
            )
            passed = quality_gate_passes(
                pass_rate=latest_run.pass_rate,
                min_pass_rate=min_pass_rate,
            )
            # The verdict is recorded on the release whichever way it went,
            # so "was this shipped over a red gate?" is answerable later
            # without re-deriving it from evaluation history.
            release.quality_gate_status = "passed" if passed else "failed"
            release.quality_gate_run_id = latest_run.id
            if not passed and not force:
                raise QualityGateBlocked(
                    f"Release {version} failed quality gate "
                    f"(pass rate {latest_run.pass_rate:.2f} < {min_pass_rate:.2f})",
                    run_id=latest_run.id,
                    pass_rate=latest_run.pass_rate,
                    min_pass_rate=min_pass_rate,
                )
        await self._publish_locked(agent, release, user_id)
        await self.repo.db.commit()
        await self.repo.db.refresh(release)
        return release

    async def rollback_release(
        self,
        org_id: str,
        agent_id: str,
        version: int,
        user_id: str | None = None,
    ) -> AgentRelease:
        agent = await self._locked_agent(org_id, agent_id)
        if agent is None:
            raise ValueError("agent not found")
        target = await self.get_release(org_id, agent_id, version)
        if target is None:
            raise ValueError("agent release not found")
        release = await self._create_release_locked(
            agent,
            _snapshot(target),
            user_id=user_id,
            change_note=f"Rollback to version {version}",
            publish=True,
        )
        await self.repo.db.commit()
        await self.repo.db.refresh(release)
        return release

    async def _resolve_model_for_tier(
        self, org_id: str, recommended_tier: str, active_models: list[Model] | None = None
    ) -> str | None:
        models = active_models
        if models is None:
            res = await self.repo.db.execute(
                select(Model).where(Model.org_id == org_id, Model.active.is_(True))
            )
            models = list(res.scalars().all())
        if not models:
            return None
        # Try matching recommended tier
        for m in models:
            if getattr(m, "tier", None) == recommended_tier:
                return m.id
        # Fallback to first available active model
        return models[0].id

    def _build_virtual_agent(
        self,
        org_id: str,
        blueprint: SystemAgentBlueprint,
        model_id: str | None,
        is_pinned: bool = False,
        temperature: float | None = None,
    ) -> Agent:
        now = utc_now()
        agent = Agent(
            id=blueprint.id,
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
            temperature=temperature if temperature is not None else blueprint.temperature,
            enable_thinking=blueprint.enable_thinking,
            a2a_exposed=blueprint.a2a_exposed,
            auto_rollback_enabled=blueprint.auto_rollback_enabled,
            template_key=blueprint.key,
            is_customized=False,
            created_at=now,
            updated_at=now,
        )
        agent.is_pinned = is_pinned
        return agent

    async def runtime_agent(
        self, org_id: str, agent_id: str, release_id: str | None = None
    ) -> Agent | RuntimeAgent:
        agent = await self.get(org_id, agent_id)
        if agent is None:
            raise ValueError("agent not found")
        if not release_id or release_id == agent.active_release_id:
            return agent
        res = await self.repo.db.execute(
            select(AgentRelease).where(
                AgentRelease.id == release_id,
                AgentRelease.org_id == org_id,
                AgentRelease.agent_id == agent.id,
            )
        )
        release = res.scalar_one_or_none()
        if release is None:
            raise ValueError("agent release not found")
        return RuntimeAgent(
            id=agent.id,
            org_id=agent.org_id,
            created_by_user_id=agent.created_by_user_id,
            name=agent.name,
            active_release_id=release.id,
            latest_release_number=release.version,
            created_at=agent.created_at,
            updated_at=agent.updated_at,
            enable_thinking=getattr(agent, "enable_thinking", None),
            **_snapshot(release),
        )

    async def _locked_agent(self, org_id: str, agent_id: str) -> Agent | None:
        res = await self.repo.db.execute(
            select(Agent)
            .where(Agent.id == agent_id, Agent.org_id == org_id)
            .with_for_update()
        )
        return res.scalar_one_or_none()

    async def _validate_model(self, org_id: str, model_id: str) -> None:
        model = await self.model_repo.get(org_id, model_id)
        if model is None or not model.active:
            raise ValueError("model not found or inactive")

    async def _create_release_locked(
        self,
        agent: Agent,
        overrides: dict,
        *,
        user_id: str | None,
        change_note: str,
        publish: bool,
    ) -> AgentRelease:
        config = _snapshot(agent, overrides)
        agent.latest_release_number += 1
        release = AgentRelease(
            org_id=agent.org_id,
            agent_id=agent.id,
            version=agent.latest_release_number,
            status="draft",
            **config,
            change_note=change_note,
            config_hash=_config_hash(config),
            created_by_user_id=user_id,
        )
        self.repo.db.add(release)
        await self.repo.db.flush()
        if publish:
            await self._publish_locked(agent, release, user_id)
        return release

    async def _publish_locked(
        self, agent: Agent, release: AgentRelease, user_id: str | None
    ) -> None:
        if agent.active_release_id:
            res = await self.repo.db.execute(
                select(AgentRelease).where(
                    AgentRelease.id == agent.active_release_id,
                    AgentRelease.org_id == agent.org_id,
                )
            )
            current = res.scalar_one_or_none()
            if current is not None:
                current.status = "archived"
        for field, value in _snapshot(release).items():
            setattr(agent, field, value)
        release.status = "published"
        release.published_by_user_id = user_id
        release.published_at = utc_now()
        agent.active_release_id = release.id

    async def delete(self, org_id: str, id: str) -> bool:
        return await self.repo.delete(org_id, id)

    async def reset_to_template(self, org_id: str, id: str) -> Agent:
        """Reset an agent override back to the system blueprint default, deleting the custom DB record."""
        # Find matched blueprint
        matched_blueprint = None
        for bp in SYSTEM_AGENT_BLUEPRINTS.values():
            if bp.id == id or bp.key == id or bp.name.lower() == id.lower():
                matched_blueprint = bp
                break

        # Check DB row by id or template_key
        db_agent = await self.repo.get(org_id, id)
        if db_agent is None and matched_blueprint is not None:
            db_agent = await self.repo.db.scalar(
                select(Agent).where(
                    Agent.org_id == org_id,
                    Agent.template_key == matched_blueprint.key,
                )
            )

        if db_agent is not None:
            if not matched_blueprint and db_agent.template_key:
                matched_blueprint = SYSTEM_AGENT_BLUEPRINTS.get(db_agent.template_key)
            if not matched_blueprint:
                raise ValueError("Agent is a custom agent and cannot be reset to a system template")

            # Delete releases
            await self.repo.db.execute(
                delete(AgentRelease).where(
                    AgentRelease.org_id == org_id,
                    AgentRelease.agent_id == db_agent.id,
                )
            )
            # Delete cheap settings if any
            await self.repo.db.execute(
                delete(OrgAgentSettings).where(
                    OrgAgentSettings.org_id == org_id,
                    OrgAgentSettings.template_key == matched_blueprint.key,
                )
            )
            # Delete the agent DB record
            await self.repo.db.delete(db_agent)
            await self.repo.db.commit()

        if matched_blueprint is None:
            raise ValueError("Template blueprint not found")

        # Return the clean virtual blueprint agent
        model_id = await self._resolve_model_for_tier(org_id, matched_blueprint.recommended_tier)
        return self._build_virtual_agent(
            org_id=org_id,
            blueprint=matched_blueprint,
            model_id=model_id,
            is_pinned=matched_blueprint.is_pinned_by_default,
        )

    async def list(self, org_id: str) -> list[Agent]:
        # 1. Fetch DB agents (custom agents & heavy overrides)
        db_agents = await self.repo.list(org_id)

        # 2. Fetch org agent settings for cheap overrides
        settings_res = await self.repo.db.execute(
            select(OrgAgentSettings).where(OrgAgentSettings.org_id == org_id)
        )
        settings_by_key = {s.template_key: s for s in settings_res.scalars().all()}

        # 3. Track which template_keys or names are already covered by DB rows
        covered_keys = {a.template_key for a in db_agents if a.template_key}
        covered_names = {a.name.strip().lower().replace(" ", "-") for a in db_agents}

        # 4. Preload active models for org
        models_res = await self.repo.db.execute(
            select(Model).where(Model.org_id == org_id, Model.active.is_(True))
        )
        active_models = list(models_res.scalars().all())

        # Tag DB agents with is_pinned
        for a in db_agents:
            tpl_key = getattr(a, "template_key", None)
            if tpl_key and tpl_key in settings_by_key:
                a.is_pinned = settings_by_key[tpl_key].is_pinned
            else:
                a.is_pinned = True  # DB agents pinned by default

        result_agents: list[Agent] = list(db_agents)

        # 5. Inject un-overridden System Blueprints
        for blueprint in SYSTEM_AGENT_BLUEPRINTS.values():
            norm_name = blueprint.name.strip().lower().replace(" ", "-")
            if blueprint.key in covered_keys or norm_name in covered_names or blueprint.key in covered_names:
                continue

            settings = settings_by_key.get(blueprint.key)
            if settings and not settings.is_enabled:
                continue

            is_pinned = settings.is_pinned if settings else blueprint.is_pinned_by_default
            model_id = (
                settings.model_override_id
                if (settings and settings.model_override_id)
                else await self._resolve_model_for_tier(org_id, blueprint.recommended_tier, active_models)
            )
            temp = settings.temperature_override if (settings and settings.temperature_override is not None) else blueprint.temperature

            v_agent = self._build_virtual_agent(
                org_id=org_id,
                blueprint=blueprint,
                model_id=model_id,
                is_pinned=is_pinned,
                temperature=temp,
            )
            result_agents.append(v_agent)

        return result_agents

    async def get(self, org_id: str, id: str) -> Agent | None:
        # 1. Try DB lookup by exact ID
        agent = await self.repo.get(org_id, id)
        if agent is not None:
            settings = await self.repo.db.scalar(
                select(OrgAgentSettings).where(
                    OrgAgentSettings.org_id == org_id,
                    OrgAgentSettings.template_key == agent.template_key,
                )
            )
            agent.is_pinned = settings.is_pinned if settings else True
            return agent

        # 2. Check if ID matches a System Blueprint (sys-agent-* or template_key)
        matched_blueprint: SystemAgentBlueprint | None = None
        for bp in SYSTEM_AGENT_BLUEPRINTS.values():
            if bp.id == id or bp.key == id or bp.name.lower() == id.lower():
                matched_blueprint = bp
                break

        if matched_blueprint is not None:
            # Check if org has an override in DB for this template_key
            override = await self.repo.db.scalar(
                select(Agent).where(
                    Agent.org_id == org_id,
                    Agent.template_key == matched_blueprint.key,
                )
            )
            if override is not None:
                settings = await self.repo.db.scalar(
                    select(OrgAgentSettings).where(
                        OrgAgentSettings.org_id == org_id,
                        OrgAgentSettings.template_key == matched_blueprint.key,
                    )
                )
                override.is_pinned = settings.is_pinned if settings else True
                return override

            # Check OrgAgentSettings
            settings = await self.repo.db.scalar(
                select(OrgAgentSettings).where(
                    OrgAgentSettings.org_id == org_id,
                    OrgAgentSettings.template_key == matched_blueprint.key,
                )
            )
            if settings and not settings.is_enabled:
                return None

            is_pinned = settings.is_pinned if settings else matched_blueprint.is_pinned_by_default
            model_id = (
                settings.model_override_id
                if (settings and settings.model_override_id)
                else await self._resolve_model_for_tier(org_id, matched_blueprint.recommended_tier)
            )
            temp = settings.temperature_override if (settings and settings.temperature_override is not None) else matched_blueprint.temperature

            return self._build_virtual_agent(
                org_id=org_id,
                blueprint=matched_blueprint,
                model_id=model_id,
                is_pinned=is_pinned,
                temperature=temp,
            )

        # 3. Try DB lookup by exact name
        by_name = await self.repo.db.scalar(
            select(Agent).where(Agent.org_id == org_id, Agent.name == id)
        )
        if by_name is not None:
            by_name.is_pinned = True
            return by_name

        return None

    async def list_available_tools(self, org_id: str, user_id: str | None = None) -> list[dict]:
        from sqlalchemy import select

        from app.core.tools.registry import list_tools
        from app.models.customer_intelligence import (
            CalendarConnection,
            DriveConnection,
            EmailConnection,
        )
        from app.models.mcp import McpServer, McpTool

        connected_kinds: set[str] = set()
        if user_id:
            for model, kind in (
                (EmailConnection, "email"),
                (CalendarConnection, "calendar"),
                (DriveConnection, "drive"),
            ):
                result = await self.repo.db.execute(
                    select(model.id).where(
                        model.org_id == org_id,
                        model.created_by_user_id == user_id,
                        model.status == "connected",
                    ).limit(1)
                )
                if result.scalar_one_or_none() is not None:
                    connected_kinds.add(kind)

        def tool_available(name: str) -> bool:
            if name.startswith("email_"):
                return "email" in connected_kinds
            if name.startswith("calendar_"):
                return "calendar" in connected_kinds
            if name.startswith("drive_"):
                return "drive" in connected_kinds
            return True

        seen: set[str] = set()
        out: list[dict] = []
        for spec in list_tools():
            if spec.name in seen:
                continue
            seen.add(spec.name)
            out.append(
                {
                    "name": spec.name,
                    "description": spec.description,
                    "available": tool_available(spec.name),
                    "risk_tier": spec.risk_tier.value,
                }
            )
        res = await self.repo.db.execute(
            select(McpTool)
            .join(McpServer)
            .where(
                McpServer.org_id == org_id,
                McpServer.connection_status == "connected",
                McpTool.enabled.is_(True),
            )
        )
        for t in res.scalars().all():
            if t.name in seen:
                continue
            seen.add(t.name)
            out.append(
                {
                    "name": t.name,
                    "description": t.description,
                    "available": True,
                }
            )
        return out
