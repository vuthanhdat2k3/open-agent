"""LLMClient thinking parameter: enable_thinking reaches the wire only when set."""

from unittest.mock import MagicMock, patch

import pytest

from app.core.llm import LLMClient


@pytest.fixture
def client():
    return LLMClient("http://test", "sk-test", "test-model")


def _mock_response(content: str = "ok") -> MagicMock:
    resp = MagicMock()
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = []
    resp.choices = [MagicMock(message=msg)]
    resp.usage = None
    return resp


async def test_complete_thinking_false_sends_enable_thinking_false(client):
    captured: dict = {}

    async def fake_create(**kwargs):
        captured.update(kwargs)
        return _mock_response()

    with patch.object(client._client.chat.completions, "create", side_effect=fake_create):
        await client.complete([{"role": "user", "content": "hi"}], thinking=False)

    assert captured.get("extra_body") == {"enable_thinking": False}


async def test_complete_thinking_none_omits_enable_thinking(client):
    captured: dict = {}

    async def fake_create(**kwargs):
        captured.update(kwargs)
        return _mock_response()

    with patch.object(client._client.chat.completions, "create", side_effect=fake_create):
        await client.complete([{"role": "user", "content": "hi"}])

    assert "extra_body" not in captured


async def test_complete_thinking_true_omits_enable_thinking(client):
    captured: dict = {}

    async def fake_create(**kwargs):
        captured.update(kwargs)
        return _mock_response()

    with patch.object(client._client.chat.completions, "create", side_effect=fake_create):
        await client.complete([{"role": "user", "content": "hi"}], thinking=True)

    assert "extra_body" not in captured
