from datetime import datetime

import pytest

from app.core.tools.registry import BUILTIN_TOOLS
from app.customer_intelligence.contracts import CompanyRecord, NormalizedEmail
from app.customer_intelligence.matching import match_companies
from app.customer_intelligence.providers.email import McpEmailProvider
from app.customer_intelligence.security import decrypt_bytes, encrypt_bytes


class AsyncCompanyProvider:
    async def company_search(self, query: str, limit: int = 5) -> list[CompanyRecord]:
        return [
            CompanyRecord(
                company_id="acme",
                canonical_name="Acme Corporation",
                aliases=["Acme"],
                industry="Manufacturing",
                products=["Products"],
                contacts=[],
                source="test",
                updated_at=None,
            )
        ]


@pytest.mark.asyncio
async def test_match_companies_awaits_async_provider() -> None:
    email = NormalizedEmail(
        provider="fake",
        provider_message_id="message-1",
        thread_id=None,
        sender_name=None,
        sender_email="sales@acme.example",
        sender_domain="acme.example",
        recipients=[],
        subject="Acme Corporation request",
        body_text="Please send a quote.",
        body_html=None,
        attachments=[],
        received_at=datetime(2026, 8, 6),
    )

    companies = await match_companies(email, AsyncCompanyProvider())

    assert [company.company_id for company in companies] == ["acme"]


def test_credential_encryption_uses_a_fresh_nonce() -> None:
    first = encrypt_bytes(b"same credentials")
    second = encrypt_bytes(b"same credentials")

    assert first != second
    assert decrypt_bytes(first) == b"same credentials"
    assert decrypt_bytes(second) == b"same credentials"


def test_gmail_provider_normalizes_received_at_to_naive_utc() -> None:
    email = McpEmailProvider._email(
        {
            "provider": "gmail",
            "provider_message_id": "message-1",
            "sender_email": "sender@example.com",
            "sender_domain": "example.com",
            "subject": "Test",
            "body_text": "Body",
            "received_at": "2026-08-13T07:47:45+07:00",
        }
    )

    assert email.received_at == datetime(2026, 8, 13, 0, 47, 45)
    assert email.received_at.tzinfo is None


def test_gmail_provider_keeps_naive_received_at_as_utc() -> None:
    email = McpEmailProvider._email(
        {
            "provider": "gmail",
            "provider_message_id": "message-2",
            "sender_email": "sender@example.com",
            "sender_domain": "example.com",
            "subject": "Test",
            "body_text": "Body",
            "received_at": datetime(2026, 8, 13, 0, 47, 45, tzinfo=None),
        }
    )

    assert email.received_at == datetime(2026, 8, 13, 0, 47, 45)
    assert email.received_at.tzinfo is None


def test_google_tool_contracts_explain_provider_specific_arguments() -> None:
    email_search = BUILTIN_TOOLS["email_search"]
    drive_list = BUILTIN_TOOLS["drive_list_files"]
    calendar_list = BUILTIN_TOOLS["calendar_list_events"]

    assert "Gmail query syntax" in email_search.description
    assert "newer_than:1d" in email_search.input_schema["properties"]["query"]["description"]
    assert "filename substring" in drive_list.description
    assert "not raw Drive query syntax" in drive_list.input_schema["properties"]["query"]["description"]
    assert "ISO-8601" in calendar_list.description
    assert "timezone offset" in calendar_list.input_schema["properties"]["from"]["description"]


def test_oauth_state_roundtrip_and_tamper() -> None:
    from app.customer_intelligence.oauth import create_oauth_state, verify_oauth_state

    state = create_oauth_state("user-1", "org-1", "email", "google")
    payload = verify_oauth_state(state)
    assert payload["user_id"] == "user-1"
    assert payload["org_id"] == "org-1"
    assert payload["kind"] == "email"
    assert payload["provider"] == "google"

    # Tampered signature should fail
    tampered = state[:-4] + "abcd"
    with pytest.raises(ValueError, match="invalid OAuth state"):
        verify_oauth_state(tampered)

