#!/usr/bin/env python3
"""Setup Bynara provider, Agnes model, and agents via API."""
import os

import httpx

BASE_URL = os.environ.get("OPENAGENT_BASE_URL", "http://localhost:8000")
EMAIL = os.environ.get("OPENAGENT_EMAIL", "")
PASSWORD = os.environ.get("OPENAGENT_PASSWORD", "")
BYNARA_API_KEY = os.environ.get("BYNARA_API_KEY", "")

def main():
    if not EMAIL or not PASSWORD or not BYNARA_API_KEY:
        raise RuntimeError(
            "Set OPENAGENT_EMAIL, OPENAGENT_PASSWORD, and BYNARA_API_KEY before running setup"
        )

    # Login
    resp = httpx.post(f"{BASE_URL}/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
    resp.raise_for_status()
    token = resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Get org_id (from current user's memberships)
    resp = httpx.get(f"{BASE_URL}/api/auth/me", headers=headers)
    resp.raise_for_status()
    org_id = resp.json()["memberships"][0]["org_id"]
    print(f"[OK] Logged in as {EMAIL}, org: {org_id}")

    # Create Provider: Bynara
    provider_data = {
        "name": "Bynara",
        "key": "bynara",
        "base_url": "https://router.bynara.id/v1",
        "api_key": BYNARA_API_KEY,
        "is_default": False,
    }
    resp = httpx.post(f"{BASE_URL}/api/v1/providers", json=provider_data, headers=headers)
    resp.raise_for_status()
    provider = resp.json()
    provider_id = provider["id"]
    print(f"[OK] Created provider Bynara: {provider_id}")

    # Create Model: agnes-2.0-flash
    model_data = {
        "provider_id": provider_id,
        "name": "agnes-2.0-flash",
        "display_name": "Agnes 2.0 Flash",
        "tier": "frontier",
        "context_window": 200000,
        "input_cost_per_1k": 0.0,
        "output_cost_per_1k": 0.0,
        "active": True,
    }
    resp = httpx.post(f"{BASE_URL}/api/v1/models", json=model_data, headers=headers)
    resp.raise_for_status()
    model = resp.json()
    model_id = model["id"]
    print(f"✓ Created model Agnes 2.0 Flash: {model_id}")

    # Create Agents
    agents = [
        {
            "name": "Coder",
            "description": "Code generation and file edits",
            "system_prompt": (
                "You are a coding agent. Read the relevant files, plan the change, "
                "and implement it with clear, minimal diffs.\n\n"
                "IMPORTANT: When responding with HTML, CSS, or JavaScript for preview/display purposes, "
                "return it as a code block (```html, ```css, ```javascript) in your response. "
                "Do NOT use write_file for this. Users can then preview it directly in the chat UI."
            ),
            "model_id": model_id,
            "tools": ["run_code", "read_attachment"],
            "max_iterations": 16,
            "temperature": 0.2,
        },
        {
            "name": "Reviewer",
            "description": "Code review and quality feedback",
            "system_prompt": "You are a code review agent. Analyze code for quality, security, and best practices.",
            "model_id": model_id,
            "tools": ["read_attachment"],
            "max_iterations": 12,
            "temperature": 0.3,
        },
        {
            "name": "Writer",
            "description": "Content and documentation writing",
            "system_prompt": "You are a writing agent. Create clear, well-structured content and documentation.",
            "model_id": model_id,
            "tools": ["read_attachment"],
            "max_iterations": 10,
            "temperature": 0.7,
        },
    ]

    agent_ids = {}
    for agent_cfg in agents:
        resp = httpx.post(f"{BASE_URL}/api/v1/agents", json=agent_cfg, headers=headers)
        resp.raise_for_status()
        agent = resp.json()
        agent_ids[agent_cfg["name"]] = agent["id"]
        print(f"✓ Created agent {agent_cfg['name']}: {agent['id']}")

    # Create Workflow
    workflow_data = {
        "name": "Code Review Pipeline",
        "description": "Code generation followed by review",
        "graph": {
            "nodes": [
                {"id": "in", "kind": "input", "label": "input", "config": {}},
                {"id": "c", "kind": "agent", "label": "coder", "agent_id": agent_ids["Coder"], "config": {}},
                {"id": "r", "kind": "agent", "label": "reviewer", "agent_id": agent_ids["Reviewer"], "config": {}},
                {"id": "out", "kind": "output", "label": "output", "config": {}},
            ],
            "edges": [
                {"from_": "in", "to": "c"},
                {"from_": "c", "to": "r"},
                {"from_": "r", "to": "out"},
            ],
        },
    }
    resp = httpx.post(f"{BASE_URL}/api/v1/workflows", json=workflow_data, headers=headers)
    resp.raise_for_status()
    workflow = resp.json()
    print(f"✓ Created workflow 'Code Review Pipeline': {workflow['id']}")

    print("\n✅ Setup complete!")
    print(f"   Provider: Bynara ({provider_id})")
    print(f"   Model: Agnes 2.0 Flash ({model_id})")
    print(f"   Agents: {', '.join(agent_ids.keys())}")
    print("   Workflow: Code Review Pipeline")

if __name__ == "__main__":
    main()
