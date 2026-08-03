from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

from app.config import get_settings
from app.models.agent_identity import AgentIdentity


def exchange_token_for_agent(
    user_id: str,
    org_id: str,
    agent_identity: AgentIdentity,
    target_audience: str,
    expires_delta: timedelta | None = None,
    parent_act: dict[str, Any] | None = None,
    parent_delegation_chain: list[dict[str, Any]] | None = None,
) -> str:
    """Performs RFC 8693 internal token exchange for an AgentIdentity.

    Exchanges user context (or parent delegation chain) for a short-lived,
    audience-restricted agent access token with an RFC 8693 ``act`` claim and
    delegation chain.
    """
    if not agent_identity.enabled:
        raise ValueError(f"Agent identity '{agent_identity.id}' is disabled")

    # Check allowed audiences if configured
    if (
        agent_identity.allowed_audiences
        and "*" not in agent_identity.allowed_audiences
        and target_audience not in agent_identity.allowed_audiences
    ):
        raise ValueError(
            f"Audience '{target_audience}' not allowed for agent identity '{agent_identity.id}'"
        )

    settings = get_settings()
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=15))

    # Construct RFC 8693 act claim
    if parent_act:
        act_claim: dict[str, Any] = {"sub": agent_identity.subject, "act": parent_act}
    else:
        act_claim = {"sub": user_id}

    # Construct delegation chain
    if parent_delegation_chain:
        delegation_chain = list(parent_delegation_chain) + [
            {
                "type": "agent",
                "identity_id": agent_identity.id,
                "agent_id": agent_identity.agent_id,
                "subject": agent_identity.subject,
            }
        ]
    else:
        delegation_chain = [
            {"type": "user", "id": user_id},
            {
                "type": "agent",
                "identity_id": agent_identity.id,
                "agent_id": agent_identity.agent_id,
                "subject": agent_identity.subject,
            },
        ]

    payload = {
        "sub": agent_identity.subject,
        "iss": "openagent:internal",
        "aud": target_audience,
        "org_id": org_id,
        "agent_id": agent_identity.agent_id,
        "actor_agent_identity_id": agent_identity.id,
        "on_behalf_of_user_id": user_id,
        "act": act_claim,
        "delegation_chain": delegation_chain,
        "token_type": "urn:ietf:params:oauth:token-type:access_token",
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }

    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def verify_agent_token(token: str, expected_audience: str | None = None) -> dict[str, Any]:
    """Verifies and decodes an agent access token.

    If expected_audience is specified, validates that token's aud claim matches.
    """
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"verify_aud": False},
        )
    except jwt.PyJWTError as e:
        raise ValueError(f"Invalid agent token: {e}") from e

    if expected_audience:
        aud = payload.get("aud")
        if aud != expected_audience and aud != "*":
            raise ValueError(
                f"Token audience mismatch: expected '{expected_audience}', got '{aud}'"
            )

    return payload
