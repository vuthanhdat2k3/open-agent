"""Production-like evaluation quality-gate smoke test."""

from __future__ import annotations

import uuid

from e2e_agent_releases import Client, wait_until_ready


def run(base_url: str = "http://127.0.0.1:3000") -> None:
    wait_until_ready(base_url)
    client = Client(base_url)
    suffix = uuid.uuid4().hex[:10]
    registration = client.request(
        "POST",
        "/api/auth/register",
        {
            "email": f"eval-e2e-{suffix}@example.com",
            "password": "Evaluation-E2E-Password-123!",
            "org_name": f"Evaluation E2E {suffix}",
        },
        expected=201,
    )
    client.token = registration["access_token"]
    provider = client.request(
        "POST",
        "/api/providers",
        {
            "key": f"eval-e2e-{suffix}",
            "name": f"Evaluation E2E {suffix}",
            "base_url": "http://localhost:9999/v1",
            "api_key": "test",
        },
        expected=201,
    )
    model = client.request(
        "POST",
        "/api/models",
        {
            "provider_id": provider["id"],
            "name": f"eval-model-{suffix}",
            "display_name": "Evaluation E2E Model",
        },
        expected=201,
    )
    agent = client.request(
        "POST",
        "/api/agents",
        {
            "name": f"Evaluation Agent {suffix}",
            "model_id": model["id"],
            "system_prompt": "Return deterministic answers.",
        },
        expected=201,
    )
    suite = client.request(
        "POST",
        "/api/evaluations/suites",
        {
            "name": f"Quality Gate {suffix}",
            "agent_id": agent["id"],
            "cases": [
                {"input": "one", "expected_output": "one"},
                {"input": "two", "expected_output": "two"},
            ],
        },
        expected=201,
    )
    case_one, case_two = suite["cases"]
    baseline = client.request(
        "POST",
        f"/api/evaluations/suites/{suite['id']}/runs",
        {
            "agent_release_id": agent["active_release_id"],
            "execution_mode": "recorded",
            "recorded_outputs": [
                {"case_id": case_one["id"], "output": "one", "latency_ms": 10},
                {"case_id": case_two["id"], "output": "two", "latency_ms": 10},
            ],
        },
        expected=201,
    )
    assert baseline["pass_rate"] == 1.0 and baseline["dataset_version"] == 1

    case_three = client.request(
        "POST",
        f"/api/evaluations/suites/{suite['id']}/cases",
        {"input": "three", "expected_output": "three"},
        expected=201,
    )
    assert case_three["added_in_version"] == 2
    candidate = client.request(
        "POST",
        f"/api/evaluations/suites/{suite['id']}/runs",
        {
            "agent_release_id": agent["active_release_id"],
            "baseline_run_id": baseline["id"],
            "execution_mode": "recorded",
            "recorded_outputs": [
                {"case_id": case_one["id"], "output": "wrong", "latency_ms": 20},
                {"case_id": case_two["id"], "output": "two", "latency_ms": 10},
            ],
        },
        expected=201,
    )
    assert candidate["dataset_version"] == 2
    assert candidate["passed_cases"] == 1 and candidate["total_cases"] == 3

    results = client.request(
        "GET", f"/api/evaluations/runs/{candidate['id']}/results"
    )
    assert len(results) == 3
    missing = next(item for item in results if item["case_id"] == case_three["id"])
    assert "recorded output missing" in missing["error"]
    comparison = client.request(
        "GET",
        f"/api/evaluations/runs/{candidate['id']}/compare/{baseline['id']}",
    )
    assert comparison["regressed_case_ids"] == [case_one["id"]]
    print("EVALUATION E2E PASS: versioned dataset, baseline, regression")


if __name__ == "__main__":
    run()

