from __future__ import annotations

from typing import Any

import httpx

from app.core.guardrails.injection import wrap_untrusted_if_flagged
from app.core.guardrails.secrets import scan_and_redact
from app.core.tools.paths import safe_url


async def fetch_external_agent_card(agent_card_url: str) -> dict[str, Any]:
    """Fetches an external Agent Card JSON document safely (SSRF guarded)."""
    validated_url = safe_url(agent_card_url)
    if not validated_url:
        raise ValueError(f"SSRF guard blocked access to URL '{agent_card_url}'")

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(validated_url)
        resp.raise_for_status()
        return resp.json()


async def call_external_agent_endpoint(
    endpoint_url: str,
    token: str,
    task_input: str,
    agent_id: str | None = None,
) -> str:
    """Executes a task on an external A2A agent endpoint safely.

    Parameters
    ----------
    endpoint_url : str
        Target A2A endpoint URL. Must pass SSRF safe_url check.
    token : str
        Exchanged RFC 8693 Bearer token.
    task_input : str
        Input prompt / task description.
    agent_id : str | None
        Target agent ID if specified in payload.

    Returns
    -------
    str
        Untrusted-wrapped and secret-redacted output string.
    """
    validated_url = safe_url(endpoint_url)
    if not validated_url:
        raise ValueError(f"SSRF guard blocked access to endpoint URL '{endpoint_url}'")

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {
        "input": task_input,
    }
    if agent_id:
        payload["agent_id"] = agent_id

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(validated_url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    # Extract output from response data
    if isinstance(data, dict):
        raw_output = data.get("output") or data.get("result") or str(data)
    else:
        raw_output = str(data)

    # Process output: external agent output is treated as untrusted
    redacted_output, _ = scan_and_redact(raw_output)
    safe_output = wrap_untrusted_if_flagged(redacted_output, source="external_agent")
    return safe_output
