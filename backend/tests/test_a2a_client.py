from __future__ import annotations

import pytest

from app.a2a.client import call_external_agent_endpoint, fetch_external_agent_card
from app.core.tools.registry import BUILTIN_TOOLS


@pytest.mark.asyncio
async def test_a2a_client_ssrf_blocked():
    # Loopback IP should be blocked by safe_url SSRF check
    with pytest.raises(ValueError, match="SSRF guard blocked access"):
        await fetch_external_agent_card("http://127.0.0.1:8000/.well-known/agent-card.json")

    with pytest.raises(ValueError, match="SSRF guard blocked access"):
        await call_external_agent_endpoint("http://169.254.169.254/latest/meta-data", "token", "test")


@pytest.mark.asyncio
async def test_call_external_agent_risk_tier():
    spec = BUILTIN_TOOLS.get("call_external_agent")
    assert spec is not None
    assert spec.risk_tier.value == "network"
