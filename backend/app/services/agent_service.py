from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select

from app.db.base import utc_now
from app.evals.quality_gate import quality_gate_passes
from app.models.agent import Agent
from app.models.agent_release import AgentRelease
from app.models.evaluation import EvaluationRun, EvaluationSuite
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


def _snapshot(source: Agent | AgentRelease, overrides: dict | None = None) -> dict:
    values = {field: getattr(source, field) for field in RELEASE_CONFIG_FIELDS}
    values.update({k: v for k, v in (overrides or {}).items() if k in RELEASE_CONFIG_FIELDS})
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
        if m is None:
            raise ValueError("model not found")
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
            raise ValueError("agent not found")
        if "allowed_risk_tiers" in data and not data["allowed_risk_tiers"]:
            data.pop("allowed_risk_tiers")
        if "model_id" in data:
            await self._validate_model(org_id, data["model_id"])

        config_changes = {k: v for k, v in data.items() if k in RELEASE_CONFIG_FIELDS}
        for field in ("name",):
            if field in data:
                setattr(agent, field, data[field])
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

    async def runtime_agent(
        self, org_id: str, agent_id: str, release_id: str | None = None
    ) -> Agent | RuntimeAgent:
        agent = await self.repo.get(org_id, agent_id)
        if agent is None:
            raise ValueError("agent not found")
        if not release_id or release_id == agent.active_release_id:
            return agent
        res = await self.repo.db.execute(
            select(AgentRelease).where(
                AgentRelease.id == release_id,
                AgentRelease.org_id == org_id,
                AgentRelease.agent_id == agent_id,
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
        if await self.model_repo.get(org_id, model_id) is None:
            raise ValueError("model not found")

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

    async def list(self, org_id: str) -> list[Agent]:
        return await self.repo.list(org_id)

    async def get(self, org_id: str, id: str) -> Agent | None:
        return await self.repo.get(org_id, id)

    async def list_available_tools(self, org_id: str) -> list[dict]:
        from sqlalchemy import select

        from app.core.tools.registry import list_tools
        from app.models.mcp import McpServer, McpTool

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
                    "available": True,
                    "risk_tier": spec.risk_tier.value,
                }
            )
        res = await self.repo.db.execute(
            select(McpTool)
            .join(McpServer)
            .where(McpServer.org_id == org_id, McpTool.enabled.is_(True))
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
