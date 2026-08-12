from datetime import datetime

import pytest

from app.core.tools.registry import BUILTIN_TOOLS
from app.customer_intelligence.contracts import CompanyRecord, NormalizedEmail
from app.customer_intelligence.matching import match_companies
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
