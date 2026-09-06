from __future__ import annotations

import httpx
import pytest

from app.core.tools import web_search as web_search_module
from app.core.tools.types import ToolContext


def _ctx() -> ToolContext:
    return ToolContext(db=None, workspace_dir=".")


class _FakeSettings:
    def __init__(self, searxng_url: str, tinyfish_api_key: str = "") -> None:
        self.searxng_url = searxng_url
        self.tinyfish_api_key = tinyfish_api_key


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


async def test_searxng_empty_results_falls_back_to_ddg(monkeypatch: pytest.MonkeyPatch) -> None:
    """SearXNG answers HTTP 200 with an empty result list when every engine
    it aggregates is rate-limited/CAPTCHA'd — that's not an exception, so it
    must still fall through to the direct-DDG path instead of returning
    "No search results found" while a working fallback sits unused.
    """
    monkeypatch.setattr(web_search_module, "get_settings", lambda: _FakeSettings("http://searxng:8080"))

    def handler(request: httpx.Request) -> httpx.Response:
        if "searxng" in request.url.host:
            return httpx.Response(200, json={"results": []})
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


async def test_all_tiers_empty_falls_back_to_tinyfish(monkeypatch: pytest.MonkeyPatch) -> None:
    """When both SearXNG and the DDG scrape come up empty, a configured
    TinyFish API key is the 3rd and final fallback tier."""
    monkeypatch.setattr(
        web_search_module, "get_settings", lambda: _FakeSettings("http://searxng:8080", tinyfish_api_key="tf-key")
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if "searxng" in request.url.host:
            return httpx.Response(200, json={"results": []})
        if request.url.host == "html.duckduckgo.com":
            return httpx.Response(200, text="")
        assert request.url.host == "api.search.tinyfish.ai"
        assert request.headers["X-API-Key"] == "tf-key"
        return httpx.Response(
            200,
            json={"results": [{"title": "TinyFish Result", "url": "https://tf-result.com", "snippet": "a snippet"}]},
        )

    monkeypatch.setattr(httpx, "AsyncClient", _mock_client(handler))

    out = await web_search_module._web_search({"query": "test"}, _ctx())
    assert "TinyFish Result" in out
    assert "tf-result.com" in out


async def test_no_tinyfish_key_returns_no_results_when_all_tiers_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without a configured key, the TinyFish tier stays inert — behavior
    must be unchanged from before this tier existed."""
    monkeypatch.setattr(web_search_module, "get_settings", lambda: _FakeSettings("http://searxng:8080"))

    def handler(request: httpx.Request) -> httpx.Response:
        if "searxng" in request.url.host:
            return httpx.Response(200, json={"results": []})
        assert request.url.host == "html.duckduckgo.com"
        return httpx.Response(200, text="")

    monkeypatch.setattr(httpx, "AsyncClient", _mock_client(handler))

    out = await web_search_module._web_search({"query": "test"}, _ctx())
    assert out == "No search results found"


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
