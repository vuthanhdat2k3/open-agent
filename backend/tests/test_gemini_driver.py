from __future__ import annotations

from copy import deepcopy

from app.core.providers.gemini_driver import GeminiDriver
from app.core.tools import builtins as _builtin_tools  # noqa: F401
from app.core.tools.registry import BUILTIN_TOOLS
from app.core.tools.types import tool_to_openai_schema

EMAIL_TOOL_NAMES = (
    "email_list_new",
    "email_get",
    "company_search",
    "memory_recall",
    "email_create_draft",
    "email_send",
    "email_forward",
    "email_reply",
    "email_remove_label",
    "email_apply_label",
    "email_list_labels",
    "email_restore",
    "email_archive",
    "email_unstar",
    "email_trash",
    "email_star",
    "email_mark_unread",
    "email_mark_read",
    "email_search",
)


def _contains_key(value: object, key: str) -> bool:
    if isinstance(value, dict):
        return key in value or any(_contains_key(item, key) for item in value.values())
    if isinstance(value, list):
        return any(_contains_key(item, key) for item in value)
    return False


def test_gemini_payload_normalizes_email_tool_schemas_without_mutating_input() -> None:
    tools = [tool_to_openai_schema(BUILTIN_TOOLS[name]) for name in EMAIL_TOOL_NAMES]
    original = deepcopy(tools)
    payload = GeminiDriver("https://example.test/v1beta", "key", "gemini-test")._payload(
        [{"role": "user", "content": "ping"}], tools, 0.7
    )

    parameters = [
        declaration["parameters"]
        for declaration in payload["tools"][0]["functionDeclarations"]
    ]
    assert len(parameters) == len(EMAIL_TOOL_NAMES)
    assert not any(_contains_key(schema, "additionalProperties") for schema in parameters)
    assert tools == original


def test_gemini_payload_converts_nullable_union_schema() -> None:
    tools = [
        {
            "type": "function",
            "function": {
                "name": "nullable_tool",
                "description": "test",
                "parameters": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "value": {
                            "type": ["string", "null"],
                            "default": None,
                        }
                    },
                },
            },
        }
    ]

    parameters = GeminiDriver("https://example.test/v1beta", "key", "gemini-test")._payload(
        [{"role": "user", "content": "ping"}], tools, 0.7
    )["tools"][0]["functionDeclarations"][0]["parameters"]

    value_schema = parameters["properties"]["value"]
    assert value_schema["type"] == "string"
    assert value_schema["nullable"] is True
    assert "default" not in value_schema
    assert "additionalProperties" not in parameters



def test_gemini_payload_maps_tool_call_id_to_declared_function_name() -> None:
    messages = [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "delegate_to_email_intelligence-0-abc12345",
                    "type": "function",
                    "function": {
                        "name": "delegate_to_email_intelligence",
                        "arguments": '{"instruction":"find mail"}',
                    },
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "delegate_to_email_intelligence-0-abc12345",
            "content": "No emails found.",
        },
    ]

    payload = GeminiDriver("https://example.test/v1beta", "key", "gemini-test")._payload(
        messages, None, 0.7
    )

    response = payload["contents"][1]["parts"][0]["functionResponse"]
    assert response["name"] == "delegate_to_email_intelligence"
