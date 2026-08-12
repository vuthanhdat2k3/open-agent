from __future__ import annotations

from app.core.providers.anthropic_driver import AnthropicDriver


def test_anthropic_payload_maps_forced_function_choice() -> None:
    driver = AnthropicDriver("https://example.test", "key", "claude-test")
    payload = driver._request_payload(
        [{"role": "user", "content": "find emails"}],
        [],
        0.7,
        tool_choice={"type": "function", "function": {"name": "delegate_to_email_intelligence"}},
    )
    assert payload["tool_choice"] == {
        "type": "tool",
        "name": "delegate_to_email_intelligence",
    }


def test_anthropic_payload_keeps_auto_default() -> None:
    driver = AnthropicDriver("https://example.test", "key", "claude-test")
    payload = driver._request_payload(
        [{"role": "user", "content": "hello"}], [], 0.7, tool_choice="auto"
    )
    assert "tool_choice" not in payload
