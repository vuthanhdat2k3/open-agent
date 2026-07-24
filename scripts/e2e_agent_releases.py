"""Production-like Agent Releases smoke test through the frontend API proxy."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import time
import urllib.error
import urllib.request
import uuid
from http.cookiejar import CookieJar
from typing import Any


class Client:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.token: str | None = None
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(CookieJar())
        )

    def request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        expected: int = 200,
    ) -> Any:
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=json.dumps(body).encode() if body is not None else None,
            headers=headers,
            method=method,
        )
        try:
            with self.opener.open(request, timeout=15) as response:
                payload = response.read()
                status = response.status
        except urllib.error.HTTPError as exc:
            payload = exc.read()
            status = exc.code
        if status != expected:
            raise RuntimeError(
                f"{method} {path}: expected {expected}, got {status}: "
                f"{payload.decode(errors='replace')}"
            )
        return json.loads(payload) if payload else None


def wait_until_ready(base_url: str, timeout_s: int = 120) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{base_url.rstrip('/')}/login", timeout=3) as response:
                if response.status == 200:
                    return
        except (OSError, urllib.error.URLError):
            time.sleep(2)
    raise TimeoutError(f"frontend did not become ready within {timeout_s}s")


def run(base_url: str) -> None:
    wait_until_ready(base_url)
    client = Client(base_url)
    suffix = uuid.uuid4().hex[:10]
    registration = client.request(
        "POST",
        "/api/auth/register",
        {
            "email": f"release-e2e-{suffix}@example.com",
            "password": "Release-E2E-Password-123!",
            "org_name": f"Release E2E {suffix}",
        },
        expected=201,
    )
    client.token = registration["access_token"]

    provider = client.request(
        "POST",
        "/api/providers",
        {
            "key": f"release-e2e-{suffix}",
            "name": f"Release E2E {suffix}",
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
            "name": f"release-model-{suffix}",
            "display_name": "Release E2E Model",
        },
        expected=201,
    )
    agent = client.request(
        "POST",
        "/api/agents",
        {
            "name": f"Release Agent {suffix}",
            "model_id": model["id"],
            "system_prompt": "release one",
        },
        expected=201,
    )
    assert agent["latest_release_number"] == 1

    def create_draft(label: str) -> dict[str, Any]:
        concurrent_client = Client(base_url)
        concurrent_client.token = client.token
        return concurrent_client.request(
            "POST",
            f"/api/agents/{agent['id']}/releases",
            {
                "system_prompt": f"release {label}",
                "change_note": f"E2E concurrent draft {label}",
            },
            expected=201,
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        drafts = list(executor.map(create_draft, ("two", "three")))
    assert sorted(item["version"] for item in drafts) == [2, 3]
    assert all(item["status"] == "draft" for item in drafts)
    draft = min(drafts, key=lambda item: item["version"])
    unchanged = client.request("GET", f"/api/agents/{agent['id']}")
    assert unchanged["system_prompt"] == "release one"

    published = client.request(
        "POST", f"/api/agents/{agent['id']}/releases/{draft['version']}/publish"
    )
    assert published["status"] == "published"
    active = client.request("GET", f"/api/agents/{agent['id']}")
    assert active["system_prompt"] == "release two"

    rollback = client.request(
        "POST", f"/api/agents/{agent['id']}/releases/1/rollback", expected=201
    )
    assert rollback["version"] == 4 and rollback["system_prompt"] == "release one"
    releases = client.request("GET", f"/api/agents/{agent['id']}/releases")
    assert [item["version"] for item in releases] == [4, 3, 2, 1]
    print("AGENT RELEASE E2E PASS: concurrent draft, publish, rollback")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:3000")
    args = parser.parse_args()
    run(args.base_url)
