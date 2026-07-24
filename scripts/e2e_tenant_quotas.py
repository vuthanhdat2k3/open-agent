"""Production-like tenant quota smoke test through the frontend proxy."""

from __future__ import annotations

import concurrent.futures
import json
import urllib.error
import urllib.request
import uuid
from typing import Any

from e2e_agent_releases import Client, wait_until_ready


def _request_status(
    base_url: str,
    token: str,
    method: str,
    path: str,
    body: dict[str, Any],
) -> tuple[int, dict[str, Any] | None]:
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}{path}",
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = response.read()
            status = response.status
    except urllib.error.HTTPError as exc:
        payload = exc.read()
        status = exc.code
    return status, json.loads(payload) if payload else None


def _register(client: Client, suffix: str) -> str:
    registration = client.request(
        "POST",
        "/api/auth/register",
        {
            "email": f"quota-e2e-{suffix}@example.com",
            "password": "Quota-E2E-Password-123!",
            "org_name": f"Quota E2E {suffix}",
        },
        expected=201,
    )
    client.token = registration["access_token"]
    me = client.request("GET", "/api/auth/me")
    return me["memberships"][0]["org_id"]


def run(base_url: str = "http://127.0.0.1:3000") -> None:
    wait_until_ready(base_url)
    suffix = uuid.uuid4().hex[:10]
    client = Client(base_url)
    org_id = _register(client, f"a-{suffix}")

    provider = client.request(
        "POST",
        "/api/providers",
        {
            "key": f"quota-e2e-{suffix}",
            "name": f"Quota E2E {suffix}",
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
            "name": f"quota-model-{suffix}",
            "display_name": "Quota E2E Model",
        },
        expected=201,
    )
    quota = client.request("GET", f"/api/orgs/{org_id}/quota")
    assert quota["requests_per_minute"] == 600
    client.request(
        "PUT",
        f"/api/orgs/{org_id}/quota",
        {"max_agents": 1},
    )
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda label: _request_status(
                    base_url,
                    client.token or "",
                    "POST",
                    "/api/agents",
                    {"name": f"Quota Agent {label} {suffix}", "model_id": model["id"]},
                ),
                ("One", "Two"),
            )
        )
    statuses = sorted(status for status, _ in results)
    assert statuses == [201, 429], statuses
    first = next(payload for status, payload in results if status == 201)
    assert first is not None

    client.request(
        "PUT",
        f"/api/orgs/{org_id}/quota",
        {
            "requests_per_minute": 1,
            "max_agents": 1,
            "enforcement_mode": "observe",
        },
    )
    client.request(
        "POST",
        "/api/agents",
        {"name": f"Quota Agent Observe {suffix}", "model_id": model["id"]},
        expected=201,
    )
    for _ in range(3):
        client.request("GET", f"/api/orgs/{org_id}/quota/usage")

    client.request(
        "PUT",
        f"/api/orgs/{org_id}/quota",
        {
            "requests_per_minute": 600,
            "monthly_cost_usd": 0,
            "enforcement_mode": "enforce",
        },
    )
    client.request(
        "POST",
        "/api/chat",
        {"agent_id": first["id"], "message": "blocked", "stream": False},
        expected=429,
    )

    other = Client(base_url)
    other_org_id = _register(other, f"b-{suffix}")
    other_quota = other.request("GET", f"/api/orgs/{other_org_id}/quota")
    assert other_quota["max_agents"] is None
    assert other_quota["monthly_cost_usd"] == 100.0
    print("TENANT QUOTA E2E PASS: enforce, observe, budget, isolation")


if __name__ == "__main__":
    run()
