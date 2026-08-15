"""Offline CompanyProvider backed by the capstone evaluation fixtures."""

from __future__ import annotations

import re
from dataclasses import replace

from app.customer_intelligence.contracts import CompanyRecord
from app.evals.customer_intelligence_fixture import FIXTURE_COMPANIES


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _copy(record: CompanyRecord) -> CompanyRecord:
    return replace(
        record,
        aliases=list(record.aliases),
        products=list(record.products),
        contacts=[dict(contact) for contact in record.contacts],
    )


class FixtureCompanyProvider:
    """A deterministic, no-network CompanyProvider for demo/evaluation runs.

    The production matching contract represents unavailable data as an empty
    result. Returning no record for an unknown name lets the existing workflow
    emit its explicit ``company lookup unavailable`` warning rather than
    fabricating a company identity.
    """

    async def company_search(self, query: str, limit: int = 5) -> list[CompanyRecord]:
        normalized = _normalize(query)
        if not normalized:
            return []
        matches: list[CompanyRecord] = []
        for record in FIXTURE_COMPANIES.values():
            candidates = [record.canonical_name, *record.aliases, record.domain or ""]
            if any(normalized in _normalize(candidate) or _normalize(candidate) in normalized for candidate in candidates):
                matches.append(_copy(record))
                if len(matches) >= limit:
                    break
        return matches

    async def company_get(self, company_id: str) -> CompanyRecord | None:
        for record in FIXTURE_COMPANIES.values():
            if record.company_id == company_id:
                return _copy(record)
        return None
