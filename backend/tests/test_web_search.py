from __future__ import annotations

import httpx
import pytest

from app.core.tools import web_search as web_search_module
from app.core.tools.types import ToolContext


def _ctx() -> ToolContext:
    return ToolContext(db=None, workspace_dir=".")


class _FakeSettings:
    def __init__(self, searxng_url: str) -> None:
        self.searxng_url = searxng_url


_RealAsyncClient = httpx.AsyncClient


def _mock_client(handler):
    def factory(**kwargs):
        return _RealAsyncClient(transport=httpx.MockTransport(handler), **kwargs)

    return factory


async def test_searxng_success_returns_excerpt_and_date(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(web_search_module, "get_settings", lambda: _FakeSettings("http://searxng:8080"))

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/search"
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": "Example",
                        "url": "https://example.com",
                        "content": "an excerpt",
                        "publishedDate": "2026-08-01T00:00:00",
                    }
                ]
            },
        )

    monkeypatch.setattr(httpx, "AsyncClient", _mock_client(handler))

    out = await web_search_module._web_search({"query": "test"}, _ctx())
    assert "Example" in out
    assert "an excerpt" in out
    assert "2026-08-01" in out


async def test_searxng_failure_falls_back_to_ddg(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(web_search_module, "get_settings", lambda: _FakeSettings("http://searxng:8080"))

    def handler(request: httpx.Request) -> httpx.Response:
        if "searxng" in request.url.host:
            return httpx.Response(500)
        assert request.url.host == "html.duckduckgo.com"
        html = (
            '<a class="result__a" href="https://ddg-result.com">DDG Result</a>'
            '<a class="result__snippet">a snippet</a>'
        )
        return httpx.Response(200, text=html)

    monkeypatch.setattr(httpx, "AsyncClient", _mock_client(handler))

    out = await web_search_module._web_search({"query": "test"}, _ctx())
    assert "DDG Result" in out
    assert "ddg-result.com" in out


async def test_disabled_searxng_uses_ddg_directly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(web_search_module, "get_settings", lambda: _FakeSettings(""))

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "html.duckduckgo.com"
        return httpx.Response(200, text="")

    monkeypatch.setattr(httpx, "AsyncClient", _mock_client(handler))

    out = await web_search_module._web_search({"query": "test"}, _ctx())
    assert out == "No search results found"


async def test_missing_query_errors_without_network_call() -> None:
    out = await web_search_module._web_search({}, _ctx())
    assert out.startswith("error")
