from __future__ import annotations

import httpx
import pytest

from app.core.tools import builtins as builtins_module
from app.core.tools.types import ToolContext


def _ctx() -> ToolContext:
    return ToolContext(db=None, workspace_dir=".")


class _FakeSettings:
    def __init__(self, crawler_url: str, crawler_api_token: str = "test-token") -> None:
        self.crawler_url = crawler_url
        self.crawler_api_token = crawler_api_token


_RealAsyncClient = httpx.AsyncClient


def _mock_client(handler):
    def factory(**kwargs):
        return _RealAsyncClient(transport=httpx.MockTransport(handler), **kwargs)

    return factory


async def test_crawler_success_returns_markdown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(builtins_module, "get_settings", lambda: _FakeSettings("http://crawler:11235"))

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/crawl"
        assert request.headers["Authorization"] == "Bearer test-token"
        return httpx.Response(200, json={"results": [{"success": True, "markdown": "# Rendered content"}]})

    monkeypatch.setattr(httpx, "AsyncClient", _mock_client(handler))

    out = await builtins_module._web_fetch({"url": "https://example.com"}, _ctx())
    assert out == "# Rendered content"


async def test_crawler_dict_markdown_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(builtins_module, "get_settings", lambda: _FakeSettings("http://crawler:11235"))

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"results": [{"success": True, "markdown": {"fit_markdown": "fit", "raw_markdown": "raw"}}]},
        )

    monkeypatch.setattr(httpx, "AsyncClient", _mock_client(handler))

    out = await builtins_module._web_fetch({"url": "https://example.com"}, _ctx())
    assert out == "fit"


async def test_crawler_failure_falls_back_to_plain_fetch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(builtins_module, "get_settings", lambda: _FakeSettings("http://crawler:11235"))

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "crawler":
            return httpx.Response(500)
        assert request.url.host == "example.com"
        return httpx.Response(200, text="plain html body")

    monkeypatch.setattr(httpx, "AsyncClient", _mock_client(handler))

    out = await builtins_module._web_fetch({"url": "https://example.com"}, _ctx())
    assert out == "plain html body"


async def test_disabled_crawler_uses_plain_fetch_directly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(builtins_module, "get_settings", lambda: _FakeSettings(""))

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "example.com"
        return httpx.Response(200, text="plain html body")

    monkeypatch.setattr(httpx, "AsyncClient", _mock_client(handler))

    out = await builtins_module._web_fetch({"url": "https://example.com"}, _ctx())
    assert out == "plain html body"


async def test_blocked_url_never_reaches_crawler(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(builtins_module, "get_settings", lambda: _FakeSettings("http://crawler:11235"))

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("should not make any network call for a blocked URL")

    monkeypatch.setattr(httpx, "AsyncClient", _mock_client(handler))

    out = await builtins_module._web_fetch({"url": "http://169.254.169.254/latest/meta-data"}, _ctx())
    assert out.startswith("error: url blocked")
