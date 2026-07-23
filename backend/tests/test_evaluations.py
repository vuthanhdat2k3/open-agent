from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.session import get_db
from app.evals.cli import quality_gate_passes
from app.evals.executor import LiveAgentExecutor
from app.evals.grader import grade_output
from app.main import app
from app.models.evaluation import EvaluationCase
from app.schemas.chat import AgentLoopResult

PASSWORD = "Secret123!"


@pytest.fixture
async def async_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.fixture
def client(async_session_factory):
    async def _override_get_db():
        async with async_session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _register(client: TestClient, email: str, org_name: str) -> tuple[str, str]:
    response = client.post(
        "/api/auth/register",
        json={"email": email, "password": PASSWORD, "org_name": org_name},
    )
    assert response.status_code == 201, response.text
    token = response.json()["access_token"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    return token, me.json()["memberships"][0]["org_id"]


def _headers(token: str, org_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "X-Org-Id": org_id}


def _create_agent(client: TestClient, token: str, org_id: str) -> dict:
    headers = _headers(token, org_id)
    provider = client.post(
        "/api/providers",
        headers=headers,
        json={
            "key": "eval-provider",
            "name": "Eval Provider",
            "base_url": "http://localhost:9999/v1",
            "api_key": "test",
        },
    )
    assert provider.status_code == 201, provider.text
    model = client.post(
        "/api/models",
        headers=headers,
        json={
            "provider_id": provider.json()["id"],
            "name": "eval-model",
            "display_name": "Eval Model",
        },
    )
    assert model.status_code == 201, model.text
    agent = client.post(
        "/api/agents",
        headers=headers,
        json={
            "name": "Evaluation Agent",
            "system_prompt": "Return deterministic test answers.",
            "model_id": model.json()["id"],
        },
    )
    assert agent.status_code == 201, agent.text
    return agent.json()


def _create_suite(
    client: TestClient, token: str, org_id: str, agent_id: str
) -> dict:
    response = client.post(
        "/api/evaluations/suites",
        headers=_headers(token, org_id),
        json={
            "name": "Release quality",
            "description": "Deterministic quality gate",
            "agent_id": agent_id,
            "cases": [
                {
                    "input": "case one",
                    "expected_output": "Hello World",
                    "required_substrings": ["world"],
                    "expected_tools": ["search"],
                    "forbidden_patterns": ["secret"],
                    "max_latency_ms": 100,
                    "max_cost_usd": 0.1,
                },
                {"input": "case two", "expected_output": "Good"},
            ],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_deterministic_grader_reports_each_check() -> None:
    case = EvaluationCase(
        org_id="org",
        suite_id="suite",
        input="input",
        expected_output="Hello World",
        required_substrings=["hello"],
        expected_tools=["search"],
        forbidden_patterns=["password"],
        max_latency_ms=100,
        max_cost_usd=0.5,
        ordinal=1,
        added_in_version=1,
    )
    passing = grade_output(
        case,
        output="  hello   world ",
        observed_tools=["search"],
        latency_ms=50,
        cost_usd=0.1,
    )
    assert passing.passed
    assert passing.score == 1.0
    assert all(passing.details["checks"].values())

    failing = grade_output(
        case,
        output="password leaked",
        observed_tools=[],
        latency_ms=101,
        cost_usd=0.6,
    )
    assert not failing.passed
    assert failing.score == 0.0


def test_grader_bounds_pathological_regex_runtime() -> None:
    case = EvaluationCase(
        org_id="org",
        suite_id="suite",
        input="input",
        forbidden_patterns=["(a+)+$"],
        ordinal=1,
        added_in_version=1,
    )
    grade = grade_output(
        case,
        output=("a" * 20_000) + "!",
        observed_tools=[],
        latency_ms=0,
        cost_usd=0,
    )
    assert not grade.passed
    assert grade.details["regex_errors"]


@pytest.mark.asyncio
async def test_live_executor_propagates_agent_failure_and_cost(monkeypatch) -> None:
    async def runtime_agent(*args, **kwargs):
        return object()

    async def failed_loop(*args, **kwargs):
        return AgentLoopResult(content="", error="provider unavailable")

    monkeypatch.setattr(
        "app.evals.executor.AgentService.runtime_agent", runtime_agent
    )
    monkeypatch.setattr("app.evals.executor.run_agent_loop", failed_loop)
    with pytest.raises(RuntimeError, match="provider unavailable"):
        await LiveAgentExecutor().execute(
            object(),
            type("Suite", (), {"org_id": "org", "agent_id": "agent"})(),
            type("Case", (), {"input": "hello"})(),
            type("Release", (), {"id": "release"})(),
        )

    async def successful_loop(*args, **kwargs):
        return AgentLoopResult(
            content="ok",
            tool_calls=[{"name": "search"}],
            latency_ms=12,
            cost_usd=0.25,
        )

    monkeypatch.setattr("app.evals.executor.run_agent_loop", successful_loop)
    output = await LiveAgentExecutor().execute(
        object(),
        type("Suite", (), {"org_id": "org", "agent_id": "agent"})(),
        type("Case", (), {"input": "hello"})(),
        type("Release", (), {"id": "release"})(),
    )
    assert output.cost_usd == 0.25
    assert output.observed_tools == ["search"]


def test_quality_gate_thresholds() -> None:
    assert quality_gate_passes(pass_rate=0.95, min_pass_rate=0.95)
    assert not quality_gate_passes(pass_rate=0.94, min_pass_rate=0.95)
    assert not quality_gate_passes(
        pass_rate=1.0,
        min_pass_rate=0.95,
        latency_delta=101,
        max_latency_regression_ms=100,
    )
    assert not quality_gate_passes(
        pass_rate=1.0,
        min_pass_rate=0.95,
        cost_delta=0.11,
        max_cost_regression_usd=0.1,
    )


def test_recorded_runs_compare_regressions_and_freeze_dataset(
    client: TestClient,
) -> None:
    token, org_id = _register(client, "eval-owner@example.com", "Eval Org")
    headers = _headers(token, org_id)
    agent = _create_agent(client, token, org_id)
    suite = _create_suite(client, token, org_id, agent["id"])
    first_case, second_case = suite["cases"]

    baseline = client.post(
        f"/api/evaluations/suites/{suite['id']}/runs",
        headers=headers,
        json={
            "agent_release_id": agent["active_release_id"],
            "execution_mode": "recorded",
            "recorded_outputs": [
                {
                    "case_id": first_case["id"],
                    "output": "Hello World",
                    "observed_tools": ["search"],
                    "latency_ms": 50,
                    "cost_usd": 0.01,
                },
                {
                    "case_id": second_case["id"],
                    "output": "Good",
                    "latency_ms": 20,
                },
            ],
        },
    )
    assert baseline.status_code == 201, baseline.text
    assert baseline.json()["pass_rate"] == 1.0
    assert baseline.json()["dataset_version"] == 1

    added = client.post(
        f"/api/evaluations/suites/{suite['id']}/cases",
        headers=headers,
        json={"input": "case three", "expected_output": "New"},
    )
    assert added.status_code == 201
    assert added.json()["added_in_version"] == 2

    candidate = client.post(
        f"/api/evaluations/suites/{suite['id']}/runs",
        headers=headers,
        json={
            "agent_release_id": agent["active_release_id"],
            "baseline_run_id": baseline.json()["id"],
            "execution_mode": "recorded",
            "recorded_outputs": [
                {
                    "case_id": first_case["id"],
                    "output": "wrong",
                    "observed_tools": [],
                    "latency_ms": 150,
                    "cost_usd": 0.2,
                },
                {
                    "case_id": second_case["id"],
                    "output": "Good",
                    "latency_ms": 20,
                },
            ],
        },
    )
    assert candidate.status_code == 201, candidate.text
    candidate_body = candidate.json()
    assert candidate_body["dataset_version"] == 2
    assert candidate_body["total_cases"] == 3
    assert candidate_body["passed_cases"] == 1
    assert candidate_body["pass_rate"] == pytest.approx(1 / 3)

    results = client.get(
        f"/api/evaluations/runs/{candidate_body['id']}/results",
        headers=headers,
    )
    assert results.status_code == 200
    assert len(results.json()) == 3
    missing = next(item for item in results.json() if item["case_id"] == added.json()["id"])
    assert "recorded output missing" in missing["error"]

    comparison = client.get(
        f"/api/evaluations/runs/{candidate_body['id']}/compare/{baseline.json()['id']}",
        headers=headers,
    )
    assert comparison.status_code == 200, comparison.text
    assert comparison.json()["pass_rate_delta"] == pytest.approx(-2 / 3)
    assert comparison.json()["regressed_case_ids"] == [first_case["id"]]

    baseline_results = client.get(
        f"/api/evaluations/runs/{baseline.json()['id']}/results",
        headers=headers,
    ).json()
    assert len(baseline_results) == 2


def test_evaluation_tenant_scope_and_viewer_permissions(client: TestClient) -> None:
    owner_token, org_id = _register(
        client, "eval-rbac-owner@example.com", "Eval RBAC"
    )
    agent = _create_agent(client, owner_token, org_id)
    suite = _create_suite(client, owner_token, org_id, agent["id"])

    other_token, other_org = _register(
        client, "eval-other@example.com", "Eval Other"
    )
    hidden = client.get(
        f"/api/evaluations/suites/{suite['id']}",
        headers=_headers(other_token, other_org),
    )
    assert hidden.status_code == 404

    viewer_token, _ = _register(
        client, "eval-viewer@example.com", "Eval Viewer Home"
    )
    membership = client.post(
        f"/api/orgs/{org_id}/members",
        headers=_headers(owner_token, org_id),
        json={"email": "eval-viewer@example.com", "role": "viewer"},
    )
    assert membership.status_code == 201
    assert (
        client.get(
            f"/api/evaluations/suites/{suite['id']}",
            headers=_headers(viewer_token, org_id),
        ).status_code
        == 200
    )
    denied = client.post(
        f"/api/evaluations/suites/{suite['id']}/runs",
        headers=_headers(viewer_token, org_id),
        json={
            "agent_release_id": agent["active_release_id"],
            "execution_mode": "recorded",
        },
    )
    assert denied.status_code == 403


def test_duplicate_suite_name_returns_conflict(client: TestClient) -> None:
    token, org_id = _register(
        client, "eval-conflict@example.com", "Eval Conflict"
    )
    agent = _create_agent(client, token, org_id)
    first = _create_suite(client, token, org_id, agent["id"])
    second = client.post(
        "/api/evaluations/suites",
        headers=_headers(token, org_id),
        json={"name": "Second suite", "agent_id": agent["id"]},
    )
    assert second.status_code == 201

    duplicate = client.put(
        f"/api/evaluations/suites/{second.json()['id']}",
        headers=_headers(token, org_id),
        json={"name": first["name"]},
    )
    assert duplicate.status_code == 409
