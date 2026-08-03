from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utc_now
from app.evals.executor import EvaluationExecutor, ExecutionOutput
from app.evals.grader import grade_output
from app.evals.sampler import propose_cases
from app.models.agent import Agent
from app.models.agent_release import AgentRelease
from app.models.evaluation import (
    EvaluationCase,
    EvaluationResult,
    EvaluationRun,
    EvaluationSuite,
)
from app.models.sampling_policy import SamplingPolicy


class EvaluationService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_suite(
        self, org_id: str, data: dict, user_id: str | None = None
    ) -> EvaluationSuite:
        agent = await self._agent(org_id, data["agent_id"])
        if agent is None:
            raise ValueError("agent not found")
        cases = data.pop("cases", [])
        suite = EvaluationSuite(
            org_id=org_id,
            created_by_user_id=user_id,
            dataset_version=1,
            **data,
        )
        self.db.add(suite)
        await self.db.flush()
        for ordinal, case_data in enumerate(cases, start=1):
            self.db.add(
                EvaluationCase(
                    org_id=org_id,
                    suite_id=suite.id,
                    ordinal=ordinal,
                    added_in_version=1,
                    metadata_=case_data.pop("metadata", {}),
                    **case_data,
                )
            )
        await self.db.commit()
        await self.db.refresh(suite)
        return suite

    async def list_suites(self, org_id: str) -> list[EvaluationSuite]:
        result = await self.db.execute(
            select(EvaluationSuite)
            .where(EvaluationSuite.org_id == org_id)
            .order_by(EvaluationSuite.updated_at.desc())
        )
        return list(result.scalars().all())

    async def get_suite(
        self, org_id: str, suite_id: str
    ) -> EvaluationSuite | None:
        result = await self.db.execute(
            select(EvaluationSuite).where(
                EvaluationSuite.id == suite_id,
                EvaluationSuite.org_id == org_id,
            )
        )
        return result.scalar_one_or_none()

    async def update_suite(
        self, org_id: str, suite_id: str, data: dict
    ) -> EvaluationSuite:
        suite = await self.get_suite(org_id, suite_id)
        if suite is None:
            raise ValueError("evaluation suite not found")
        for field, value in data.items():
            setattr(suite, field, value)
        await self.db.commit()
        await self.db.refresh(suite)
        return suite

    async def delete_suite(self, org_id: str, suite_id: str) -> bool:
        suite = await self.get_suite(org_id, suite_id)
        if suite is None:
            return False
        run_count = await self.db.scalar(
            select(func.count(EvaluationRun.id)).where(
                EvaluationRun.org_id == org_id,
                EvaluationRun.suite_id == suite_id,
            )
        )
        if run_count:
            raise ValueError("evaluation suite with runs cannot be deleted")
        await self.db.delete(suite)
        await self.db.commit()
        return True

    async def list_cases(
        self, org_id: str, suite_id: str, dataset_version: int | None = None
    ) -> list[EvaluationCase]:
        suite = await self.get_suite(org_id, suite_id)
        if suite is None:
            raise ValueError("evaluation suite not found")
        version = dataset_version or suite.dataset_version
        result = await self.db.execute(
            select(EvaluationCase)
            .where(
                EvaluationCase.org_id == org_id,
                EvaluationCase.suite_id == suite_id,
                EvaluationCase.added_in_version <= version,
                # Sampled proposals are excluded until reviewed: grading a
                # case whose expected answer nobody has confirmed would turn
                # an incident into a meaningless assertion.
                EvaluationCase.approved.is_(True),
            )
            .order_by(EvaluationCase.ordinal)
        )
        return list(result.scalars().all())

    async def list_proposed_cases(self, org_id: str, suite_id: str) -> list[EvaluationCase]:
        """Sampled cases still awaiting review."""
        suite = await self.get_suite(org_id, suite_id)
        if suite is None:
            raise ValueError("evaluation suite not found")
        result = await self.db.execute(
            select(EvaluationCase)
            .where(
                EvaluationCase.org_id == org_id,
                EvaluationCase.suite_id == suite_id,
                EvaluationCase.approved.is_(False),
            )
            .order_by(EvaluationCase.ordinal)
        )
        return list(result.scalars().all())

    async def propose_from_traces(self, org_id: str, policy_id: str) -> list[EvaluationCase]:
        """Run the sampler for one policy. Proposals are not gradeable yet."""
        result = await self.db.execute(
            select(SamplingPolicy).where(
                SamplingPolicy.id == policy_id, SamplingPolicy.org_id == org_id
            )
        )
        policy = result.scalar_one_or_none()
        if policy is None:
            raise ValueError("sampling policy not found")
        return await propose_cases(self.db, policy)

    async def approve_case(self, org_id: str, case_id: str, data: dict) -> EvaluationCase:
        """Accept a proposal into the dataset.

        This is the only path that turns a sampled case into a graded one,
        and it demands the reviewer supply the expected behaviour — the
        sampler deliberately left it blank.
        """
        result = await self.db.execute(
            select(EvaluationCase).where(
                EvaluationCase.id == case_id, EvaluationCase.org_id == org_id
            )
        )
        case = result.scalar_one_or_none()
        if case is None:
            raise ValueError("evaluation case not found")
        if case.approved:
            return case

        expected_output = data.get("expected_output")
        required_substrings = data.get("required_substrings") or []
        if not expected_output and not required_substrings:
            raise ValueError(
                "approving a sampled case requires expected_output or required_substrings"
            )

        suite_result = await self.db.execute(
            select(EvaluationSuite)
            .where(EvaluationSuite.id == case.suite_id, EvaluationSuite.org_id == org_id)
            .with_for_update()
        )
        suite = suite_result.scalar_one_or_none()
        if suite is None:
            raise ValueError("evaluation suite not found")

        for field, value in data.items():
            if field == "metadata":
                case.metadata_ = value
            elif hasattr(case, field):
                setattr(case, field, value)

        # The dataset version moves at approval, not at proposal: that is the
        # moment the gradeable set actually changed.
        suite.dataset_version += 1
        case.added_in_version = suite.dataset_version
        case.approved = True
        await self.db.commit()
        await self.db.refresh(case)
        return case

    async def reject_case(self, org_id: str, case_id: str) -> bool:
        """Discard a proposal. Never touches dataset_version."""
        result = await self.db.execute(
            select(EvaluationCase).where(
                EvaluationCase.id == case_id,
                EvaluationCase.org_id == org_id,
                EvaluationCase.approved.is_(False),
            )
        )
        case = result.scalar_one_or_none()
        if case is None:
            return False
        await self.db.delete(case)
        await self.db.commit()
        return True

    async def add_case(
        self, org_id: str, suite_id: str, data: dict
    ) -> EvaluationCase:
        result = await self.db.execute(
            select(EvaluationSuite)
            .where(
                EvaluationSuite.id == suite_id,
                EvaluationSuite.org_id == org_id,
            )
            .with_for_update()
        )
        suite = result.scalar_one_or_none()
        if suite is None:
            raise ValueError("evaluation suite not found")
        ordinal_result = await self.db.execute(
            select(func.coalesce(func.max(EvaluationCase.ordinal), 0)).where(
                EvaluationCase.suite_id == suite_id
            )
        )
        suite.dataset_version += 1
        case = EvaluationCase(
            org_id=org_id,
            suite_id=suite_id,
            ordinal=int(ordinal_result.scalar_one()) + 1,
            added_in_version=suite.dataset_version,
            metadata_=data.pop("metadata", {}),
            **data,
        )
        self.db.add(case)
        await self.db.commit()
        await self.db.refresh(case)
        return case

    async def create_run(
        self,
        org_id: str,
        suite_id: str,
        agent_release_id: str,
        executor: EvaluationExecutor,
        *,
        execution_mode: str,
        baseline_run_id: str | None = None,
        user_id: str | None = None,
    ) -> EvaluationRun:
        suite = await self.get_suite(org_id, suite_id)
        if suite is None:
            raise ValueError("evaluation suite not found")
        release = await self._release(
            org_id, suite.agent_id, agent_release_id
        )
        if release is None:
            raise ValueError("agent release not found")
        if baseline_run_id:
            baseline = await self.get_run(org_id, baseline_run_id)
            if baseline is None or baseline.suite_id != suite_id:
                raise ValueError("baseline evaluation run not found")

        cases = await self.list_cases(org_id, suite_id, suite.dataset_version)
        run = EvaluationRun(
            org_id=org_id,
            suite_id=suite_id,
            agent_release_id=release.id,
            baseline_run_id=baseline_run_id,
            dataset_version=suite.dataset_version,
            execution_mode=execution_mode,
            status="running",
            total_cases=len(cases),
            triggered_by_user_id=user_id,
            started_at=utc_now(),
        )
        self.db.add(run)
        await self.db.commit()
        await self.db.refresh(run)

        latencies: list[int] = []
        total_cost = 0.0
        passed = 0
        for case in cases:
            try:
                execution = await executor.execute(self.db, suite, case, release)
                grade = grade_output(
                    case,
                    output=execution.output,
                    observed_tools=execution.observed_tools,
                    latency_ms=execution.latency_ms,
                    cost_usd=execution.cost_usd,
                )
                result = EvaluationResult(
                    org_id=org_id,
                    run_id=run.id,
                    case_id=case.id,
                    output=execution.output,
                    observed_tools=execution.observed_tools,
                    latency_ms=execution.latency_ms,
                    cost_usd=execution.cost_usd,
                    score=grade.score,
                    passed=grade.passed,
                    grader_details=grade.details,
                )
                latencies.append(execution.latency_ms)
                total_cost += execution.cost_usd
                passed += int(grade.passed)
            except Exception as exc:  # noqa: BLE001 - isolate individual cases
                result = EvaluationResult(
                    org_id=org_id,
                    run_id=run.id,
                    case_id=case.id,
                    output="",
                    observed_tools=[],
                    latency_ms=0,
                    cost_usd=0.0,
                    score=0.0,
                    passed=False,
                    grader_details={"checks": {"execution_succeeded": False}},
                    error=str(exc),
                )
            self.db.add(result)
            await self.db.commit()

        run.passed_cases = passed
        run.pass_rate = passed / len(cases) if cases else 1.0
        run.average_latency_ms = (
            sum(latencies) / len(latencies) if latencies else 0.0
        )
        run.total_cost_usd = total_cost
        run.status = "completed"
        run.completed_at = utc_now()
        await self.db.commit()
        await self.db.refresh(run)
        return run

    async def get_run(
        self, org_id: str, run_id: str
    ) -> EvaluationRun | None:
        result = await self.db.execute(
            select(EvaluationRun).where(
                EvaluationRun.id == run_id, EvaluationRun.org_id == org_id
            )
        )
        return result.scalar_one_or_none()

    async def list_runs(
        self, org_id: str, suite_id: str
    ) -> list[EvaluationRun]:
        if await self.get_suite(org_id, suite_id) is None:
            raise ValueError("evaluation suite not found")
        result = await self.db.execute(
            select(EvaluationRun)
            .where(
                EvaluationRun.org_id == org_id,
                EvaluationRun.suite_id == suite_id,
            )
            .order_by(EvaluationRun.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_results(
        self, org_id: str, run_id: str
    ) -> list[EvaluationResult]:
        if await self.get_run(org_id, run_id) is None:
            raise ValueError("evaluation run not found")
        result = await self.db.execute(
            select(EvaluationResult)
            .where(
                EvaluationResult.org_id == org_id,
                EvaluationResult.run_id == run_id,
            )
            .order_by(EvaluationResult.created_at)
        )
        return list(result.scalars().all())

    async def compare_runs(
        self, org_id: str, candidate_id: str, baseline_id: str
    ) -> dict:
        candidate = await self.get_run(org_id, candidate_id)
        baseline = await self.get_run(org_id, baseline_id)
        if candidate is None or baseline is None:
            raise ValueError("evaluation run not found")
        if candidate.suite_id != baseline.suite_id:
            raise ValueError("evaluation runs belong to different suites")
        candidate_results = {
            item.case_id: item
            for item in await self.list_results(org_id, candidate_id)
        }
        baseline_results = {
            item.case_id: item
            for item in await self.list_results(org_id, baseline_id)
        }
        common = candidate_results.keys() & baseline_results.keys()
        return {
            "candidate_run_id": candidate.id,
            "baseline_run_id": baseline.id,
            "pass_rate_delta": candidate.pass_rate - baseline.pass_rate,
            "average_latency_ms_delta": (
                candidate.average_latency_ms - baseline.average_latency_ms
            ),
            "total_cost_usd_delta": candidate.total_cost_usd - baseline.total_cost_usd,
            "regressed_case_ids": sorted(
                case_id
                for case_id in common
                if baseline_results[case_id].passed
                and not candidate_results[case_id].passed
            ),
            "improved_case_ids": sorted(
                case_id
                for case_id in common
                if not baseline_results[case_id].passed
                and candidate_results[case_id].passed
            ),
        }

    async def _agent(self, org_id: str, agent_id: str) -> Agent | None:
        result = await self.db.execute(
            select(Agent).where(Agent.id == agent_id, Agent.org_id == org_id)
        )
        return result.scalar_one_or_none()

    async def _release(
        self, org_id: str, agent_id: str, release_id: str
    ) -> AgentRelease | None:
        result = await self.db.execute(
            select(AgentRelease).where(
                AgentRelease.id == release_id,
                AgentRelease.org_id == org_id,
                AgentRelease.agent_id == agent_id,
            )
        )
        return result.scalar_one_or_none()


def recorded_outputs_from_payload(payloads: list) -> dict[str, ExecutionOutput]:
    return {
        payload.case_id: ExecutionOutput(
            output=payload.output,
            observed_tools=payload.observed_tools,
            latency_ms=payload.latency_ms,
            cost_usd=payload.cost_usd,
        )
        for payload in payloads
    }
