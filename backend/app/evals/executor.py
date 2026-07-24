from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.agent_loop import run_agent_loop
from app.models.agent_release import AgentRelease
from app.models.evaluation import EvaluationCase, EvaluationSuite
from app.services.agent_service import AgentService


@dataclass(frozen=True)
class ExecutionOutput:
    output: str
    observed_tools: list[str]
    latency_ms: int
    cost_usd: float


class EvaluationExecutor(Protocol):
    async def execute(
        self,
        db: AsyncSession,
        suite: EvaluationSuite,
        case: EvaluationCase,
        release: AgentRelease,
    ) -> ExecutionOutput: ...


class LiveAgentExecutor:
    async def execute(
        self,
        db: AsyncSession,
        suite: EvaluationSuite,
        case: EvaluationCase,
        release: AgentRelease,
    ) -> ExecutionOutput:
        agent = await AgentService(db).runtime_agent(
            suite.org_id, suite.agent_id, release.id
        )
        result = await run_agent_loop(agent, case.input, db)
        if result.error:
            raise RuntimeError(result.error)
        tools = [
            str(call.get("name") or call.get("tool_name"))
            for call in result.tool_calls
            if call.get("name") or call.get("tool_name")
        ]
        return ExecutionOutput(
            output=result.content,
            observed_tools=tools,
            latency_ms=result.latency_ms,
            cost_usd=result.cost_usd,
        )


class RecordedOutputExecutor:
    def __init__(self, outputs: dict[str, ExecutionOutput]) -> None:
        self.outputs = outputs

    async def execute(
        self,
        db: AsyncSession,
        suite: EvaluationSuite,
        case: EvaluationCase,
        release: AgentRelease,
    ) -> ExecutionOutput:
        del db, suite, release
        try:
            return self.outputs[case.id]
        except KeyError as exc:
            raise ValueError(f"recorded output missing for case {case.id}") from exc
