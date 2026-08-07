from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from app.customer_intelligence.contracts import CalendarEvent, CompanyRecord, SearchHit
from app.customer_intelligence.mcp import call_customer_intelligence_mcp


class WebSearchProvider(Protocol):
    async def web_search(self, query: str, limit: int = 5) -> list[SearchHit]: ...
    async def news_search(self, query: str, limit: int = 5, lookback_days: int = 30) -> list[SearchHit]: ...


class CompanyProvider(Protocol):
    async def company_search(self, query: str, limit: int = 5) -> list[CompanyRecord]: ...
    async def company_get(self, company_id: str) -> CompanyRecord | None: ...


class CalendarProvider(Protocol):
    async def list_events(self, *, from_: datetime, to: datetime, max_results: int = 25) -> list[CalendarEvent]: ...
    async def get_event(self, provider_event_id: str) -> CalendarEvent | None: ...
    async def create_event(self, **kwargs: Any) -> dict[str, Any]: ...
    async def update_event(self, provider_event_id: str, **kwargs: Any) -> dict[str, Any]: ...
    async def delete_event(self, provider_event_id: str) -> None: ...


def _search_hit(data: dict[str, Any]) -> SearchHit:
    return SearchHit(
        url=data.get("url", ""),
        title=data.get("title", ""),
        publisher=data.get("publisher", ""),
        published_date=data.get("published_date"),
        retrieved_date=data.get("retrieved_date", ""),
        excerpt=data.get("excerpt", ""),
        domain=data.get("domain", ""),
    )


def _company(data: dict[str, Any]) -> CompanyRecord:
    return CompanyRecord(
        company_id=data.get("company_id", ""),
        canonical_name=data.get("canonical_name", data.get("name", "")),
        aliases=data.get("aliases", []),
        industry=data.get("industry"),
        products=data.get("products", []),
        contacts=data.get("contacts", []),
        source=data.get("source", "company-mcp"),
        updated_at=data.get("updated_at"),
        domain=data.get("domain"),
    )


class McpWebSearchProvider:
    async def web_search(self, query: str, limit: int = 5) -> list[SearchHit]:
        return [_search_hit(item) for item in await call_customer_intelligence_mcp("web_search", {"query": query, "limit": limit})]

    async def news_search(self, query: str, limit: int = 5, lookback_days: int = 30) -> list[SearchHit]:
        return [_search_hit(item) for item in await call_customer_intelligence_mcp("news_search", {"query": query, "limit": limit, "lookback_days": lookback_days})]


class McpCompanyProvider:
    async def company_search(self, query: str, limit: int = 5) -> list[CompanyRecord]:
        return [_company(item) for item in await call_customer_intelligence_mcp("company_search", {"query": query, "limit": limit})]

    async def company_get(self, company_id: str) -> CompanyRecord | None:
        data = await call_customer_intelligence_mcp("company_get", {"company_id": company_id})
        return _company(data) if data else None


class McpCalendarProvider:
    def __init__(self, credentials: dict[str, Any] | None = None):
        self._credentials = credentials or {}

    def bind(self, credentials: dict[str, Any]) -> McpCalendarProvider:
        return type(self)(credentials)

    async def list_events(self, *, from_: datetime, to: datetime, max_results: int = 25) -> list[CalendarEvent]:
        provider = self._credentials.get("calendar_provider", "google")
        data = await call_customer_intelligence_mcp(
            "calendar_list_events",
            {
                "provider": provider,
                "access_token": self._credentials.get("access_token", ""),
                "from_": from_.isoformat(),
                "to": to.isoformat(),
                "max_results": max_results,
            },
        )
        return [
            self._event(item)
            for item in data
            if item.get("start_at") and item.get("end_at")
        ]

    @staticmethod
    def _event(item: dict[str, Any]) -> CalendarEvent:
        return CalendarEvent(
            provider_event_id=item.get("provider_event_id", ""),
            title=item.get("title", ""),
            start_at=datetime.fromisoformat(item["start_at"].replace("Z", "+00:00")),
            end_at=datetime.fromisoformat(item["end_at"].replace("Z", "+00:00")),
            attendees=item.get("attendees", []),
            organizer=item.get("organizer"),
            description=item.get("description"),
            location=item.get("location"),
        )

    async def get_event(self, provider_event_id: str) -> CalendarEvent | None:
        data = await call_customer_intelligence_mcp(
            "calendar_get_event",
            {"provider": self._credentials.get("calendar_provider", "google"), "access_token": self._credentials.get("access_token", ""), "provider_event_id": provider_event_id},
        )
        return self._event(data) if data and data.get("start_at") and data.get("end_at") else None

    async def create_event(self, **kwargs: Any) -> dict[str, Any]:
        return await call_customer_intelligence_mcp(
            "calendar_create_event",
            {"provider": self._credentials.get("calendar_provider", "google"), "access_token": self._credentials.get("access_token", ""), **kwargs},
        )

    async def update_event(self, provider_event_id: str, **kwargs: Any) -> dict[str, Any]:
        return await call_customer_intelligence_mcp(
            "calendar_update_event",
            {"provider": self._credentials.get("calendar_provider", "google"), "access_token": self._credentials.get("access_token", ""), "provider_event_id": provider_event_id, **kwargs},
        )

    async def delete_event(self, provider_event_id: str) -> None:
        await call_customer_intelligence_mcp(
            "calendar_delete_event",
            {"provider": self._credentials.get("calendar_provider", "google"), "access_token": self._credentials.get("access_token", ""), "provider_event_id": provider_event_id},
        )


def get_web_provider() -> WebSearchProvider:
    return McpWebSearchProvider()


def get_company_provider() -> CompanyProvider:
    return McpCompanyProvider()


def get_calendar_provider() -> CalendarProvider:
    return McpCalendarProvider()


def bind_calendar_provider(provider: CalendarProvider, credentials: dict[str, Any]) -> CalendarProvider:
    bind = getattr(provider, "bind", None)
    return bind(credentials) if callable(bind) else provider
