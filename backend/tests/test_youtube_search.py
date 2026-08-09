from __future__ import annotations

import httpx
import pytest

from app.core.tools import youtube_search as youtube_search_module
from app.core.tools.types import ToolContext


def _ctx() -> ToolContext:
    return ToolContext(db=None, workspace_dir=".")


class _FakeSettings:
    def __init__(self, youtube_api_key: str) -> None:
        self.youtube_api_key = youtube_api_key


_RealAsyncClient = httpx.AsyncClient


def _mock_client(handler):
    def factory(**kwargs):
        return _RealAsyncClient(transport=httpx.MockTransport(handler), **kwargs)

    return factory


async def test_missing_api_key_errors_without_network_call(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(youtube_search_module, "get_settings", lambda: _FakeSettings(""))

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("should not make any network call without a configured API key")

    monkeypatch.setattr(httpx, "AsyncClient", _mock_client(handler))

    out = await youtube_search_module._youtube_search({"query": "test"}, _ctx())
    assert "not configured" in out


async def test_missing_query_errors_without_network_call() -> None:
    out = await youtube_search_module._youtube_search({}, _ctx())
    assert out.startswith("error")


async def test_success_returns_formatted_results(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(youtube_search_module, "get_settings", lambda: _FakeSettings("fake-key"))

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "www.googleapis.com"
        assert request.url.params["key"] == "fake-key"
        assert request.url.params["q"] == "react flow"
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": {"videoId": "abc123"},
                        "snippet": {
                            "title": "React Flow Tutorial",
                            "channelTitle": "xyflow",
                            "publishedAt": "2026-01-01T00:00:00Z",
                            "description": "Learn React Flow",
                        },
                    }
                ]
            },
        )

    monkeypatch.setattr(httpx, "AsyncClient", _mock_client(handler))

    out = await youtube_search_module._youtube_search({"query": "react flow"}, _ctx())
    assert "React Flow Tutorial" in out
    assert "https://www.youtube.com/watch?v=abc123" in out
    assert "xyflow" in out


async def test_no_results(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(youtube_search_module, "get_settings", lambda: _FakeSettings("fake-key"))

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"items": []})

    monkeypatch.setattr(httpx, "AsyncClient", _mock_client(handler))

    out = await youtube_search_module._youtube_search({"query": "test"}, _ctx())
    assert out == "No search results found"


async def test_api_error_returns_error_string(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(youtube_search_module, "get_settings", lambda: _FakeSettings("bad-key"))

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"error": {"message": "API key not valid"}})

    monkeypatch.setattr(httpx, "AsyncClient", _mock_client(handler))

    out = await youtube_search_module._youtube_search({"query": "test"}, _ctx())
    assert out.startswith("error searching YouTube")
