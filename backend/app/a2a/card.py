from __future__ import annotations

from typing import Any

from app.models.agent import Agent


def generate_agent_card(agents: list[Agent], host_url: str = "") -> dict[str, Any]:
    """Generates an A2A Agent Card document for agents with ``a2a_exposed=True``.

    Complies with A2A v1.0 specification structure for agent capabilities discovery.
    """
    exposed_agents: list[dict[str, Any]] = []
    base_url = host_url.rstrip("/") if host_url else ""

    for agent in agents:
        if not getattr(agent, "a2a_exposed", False):
            continue
        exposed_agents.append(
            {
                "id": agent.id,
                "name": agent.name,
                "description": agent.description or "",
                "skills": agent.tools or [],
                "endpoint": f"{base_url}/a2a/tasks",
                "capabilities": {
                    "kind": agent.kind,
                    "allowed_risk_tiers": agent.allowed_risk_tiers or ["safe", "read"],
                },
                "auth": {
                    "type": "bearer",
                    "scheme": "Bearer",
                    "token_format": "RFC8693_JWT",
                },
            }
        )

    return {
        "schema_version": "1.0",
        "name": "OpenAgent Platform A2A Services",
        "description": "Publicly exposed A2A agent endpoints on OpenAgent",
        "agents": exposed_agents,
    }
