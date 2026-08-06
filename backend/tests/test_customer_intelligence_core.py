from datetime import datetime

import pytest

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
