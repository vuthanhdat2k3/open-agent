from __future__ import annotations

import pytest

from app.config import get_settings
from app.customer_intelligence.providers.fixture_company import FixtureCompanyProvider
from app.customer_intelligence.providers.research import get_company_provider
from app.evals.customer_intelligence_fixture import FIXTURE_COMPANIES


@pytest.mark.asyncio
async def test_fixture_provider_resolves_all_capstone_companies_without_network() -> None:
    provider = FixtureCompanyProvider()

    for key, expected in FIXTURE_COMPANIES.items():
        records = await provider.company_search(expected.canonical_name)
        assert records and records[0].company_id == expected.company_id, key
        assert await provider.company_get(expected.company_id) == expected

    assert await provider.company_search("Unknown Company Outside Fixture") == []
    assert await provider.company_get("not-a-fixture") is None


def test_fixture_provider_is_opt_in_and_mcp_remains_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAGENT_CI_COMPANY_PROVIDER", raising=False)
    monkeypatch.delenv("CI_COMPANY_PROVIDER", raising=False)
    get_settings.cache_clear()
    assert type(get_company_provider()).__name__ == "McpCompanyProvider"

    monkeypatch.setenv("CI_COMPANY_PROVIDER", "fixture")
    get_settings.cache_clear()
    assert isinstance(get_company_provider(), FixtureCompanyProvider)
    get_settings.cache_clear()
