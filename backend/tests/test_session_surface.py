"""Unit tests for the session event surface projection."""

from __future__ import annotations

from types import SimpleNamespace

from app.core import session_log as slog
from app.core.session_surface import (
    derive_messages,
    estimate_history_tokens,
)


def _ev(seq: int, type_: str, data: dict) -> SimpleNamespace:
    return SimpleNamespace(seq=seq, type=type_, data=data)


def test_derive_basic_user_assistant_alternation():
    events = [
        _ev(0, slog.USER_MESSAGE, {"content": "hi"}),
        _ev(1, slog.ASSISTANT_MESSAGE, {"content": "hello"}),
        _ev(2, slog.USER_MESSAGE, {"content": "how are you"}),
    ]
    msgs = derive_messages(events)
    assert [m["role"] for m in msgs] == ["user", "assistant", "user"]
    assert msgs[1]["content"] == "hello"


def test_tool_call_result_full_fidelity():
    events = [
        _ev(0, slog.USER_MESSAGE, {"content": "read the file"}),
        _ev(
            1,
            slog.ASSISTANT_MESSAGE,
            {"content": None},
        ),
        _ev(2, slog.TOOL_CALL, {"tool_call_id": "tc1", "name": "read_file", "arguments": '{"path":"a.txt"}'}),
        _ev(3, slog.TOOL_RESULT, {"tool_call_id": "tc1", "content": "file contents here"}),
        _ev(4, slog.ASSISTANT_MESSAGE, {"content": "The file says: file contents here"}),
        _ev(5, slog.USER_MESSAGE, {"content": "and now?"}),
    ]
    msgs = derive_messages(events)
    assert msgs[1]["role"] == "assistant"
    assert msgs[1]["content"] is None
    assert msgs[1]["tool_calls"] == [
        {"id": "tc1", "type": "function", "function": {"name": "read_file", "arguments": '{"path":"a.txt"}'}}
    ]
    assert msgs[2] == {"role": "tool", "tool_call_id": "tc1", "content": "file contents here"}
    # Final answer follows the tool result; the next turn sees everything.
    assert len(msgs) == 5


def test_parallel_tool_calls_keep_order_and_pairing():
    events = [
        _ev(0, slog.USER_MESSAGE, {"content": "get both"}),
        _ev(1, slog.ASSISTANT_MESSAGE, {"content": None}),
        _ev(2, slog.TOOL_CALL, {"tool_call_id": "t1", "name": "a", "arguments": "{}"}),
        _ev(3, slog.TOOL_CALL, {"tool_call_id": "t2", "name": "b", "arguments": "{}"}),
        _ev(4, slog.TOOL_RESULT, {"tool_call_id": "t1", "content": "ra"}),
        _ev(5, slog.TOOL_RESULT, {"tool_call_id": "t2", "content": "rb"}),
    ]
    msgs = derive_messages(events)
    assert [tc["id"] for tc in msgs[1]["tool_calls"]] == ["t1", "t2"]
    tools = [m for m in msgs if m["role"] == "tool"]
    assert [(m["tool_call_id"], m["content"]) for m in tools] == [("t1", "ra"), ("t2", "rb")]


def test_compaction_summary_shadows_range_and_lands_summary_node():
    events = [
        _ev(0, slog.USER_MESSAGE, {"content": "old question"}),
        _ev(1, slog.ASSISTANT_MESSAGE, {"content": "old answer"}),
        _ev(2, slog.USER_MESSAGE, {"content": "recent question"}),
        _ev(
            3,
            slog.COMPACTION_SUMMARY,
            {
                "content": "[Summary] earlier conversation",
                "surface_op": {"op": "replace", "start_seq": 0, "end_seq": 1},
                "source_seqs": [0, 1],
            },
        ),
    ]
    msgs = derive_messages(events)
    assert [m["role"] for m in msgs] == ["user", "user"]
    assert "earlier conversation" in msgs[0]["content"]
    assert msgs[1]["content"] == "recent question"


def test_crash_tail_orphan_tool_call_gets_synthetic_result():
    events = [
        _ev(0, slog.USER_MESSAGE, {"content": "run it"}),
        _ev(1, slog.ASSISTANT_MESSAGE, {"content": None}),
        _ev(2, slog.TOOL_CALL, {"tool_call_id": "tc9", "name": "run_shell", "arguments": "{}"}),
    ]
    msgs = derive_messages(events)
    tools = [m for m in msgs if m["role"] == "tool"]
    assert len(tools) == 1
    assert tools[0]["tool_call_id"] == "tc9"
    assert "interrupted" in tools[0]["content"]
    assert "error:" in tools[0]["content"]


def test_completed_tool_results_are_not_duplicated_by_repair():
    events = [
        _ev(0, slog.USER_MESSAGE, {"content": "run"}),
        _ev(1, slog.ASSISTANT_MESSAGE, {"content": None}),
        _ev(2, slog.TOOL_CALL, {"tool_call_id": "ok1", "name": "x", "arguments": "{}"}),
        _ev(3, slog.TOOL_RESULT, {"tool_call_id": "ok1", "content": "fine"}),
    ]
    msgs = derive_messages(events)
    tools = [m for m in msgs if m["role"] == "tool"]
    assert len(tools) == 1 and tools[0]["content"] == "fine"


def test_empty_events_returns_empty_history():
    assert derive_messages([]) == []


def test_estimate_history_tokens_counts_content_and_tool_args():
    msgs = [
        {"role": "user", "content": "a" * 400},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [{"id": "t", "function": {"name": "n" * 100, "arguments": "{}"}}],
        },
    ]
    tokens = estimate_history_tokens(msgs)
    assert 120 <= tokens <= 140  # (400 + ~100) // 4


def test_replace_summary_with_tool_pairing_inside_shadowed_range():
    events = [
        _ev(0, slog.USER_MESSAGE, {"content": "q1"}),
        _ev(1, slog.ASSISTANT_MESSAGE, {"content": None}),
        _ev(2, slog.TOOL_CALL, {"tool_call_id": "s1", "name": "f", "arguments": "{}"}),
        _ev(3, slog.TOOL_RESULT, {"tool_call_id": "s1", "content": "r1"}),
        _ev(4, slog.ASSISTANT_MESSAGE, {"content": "answer1"}),
        _ev(5, slog.USER_MESSAGE, {"content": "q2"}),
        _ev(
            6,
            slog.COMPACTION_SUMMARY,
            {
                "content": "[Summary] q1..answer1",
                "surface_op": {"op": "replace", "start_seq": 0, "end_seq": 4},
                "source_seqs": [0, 1, 2, 3, 4],
            },
        ),
    ]
    msgs = derive_messages(events)
    roles = [m["role"] for m in msgs]
    assert roles == ["user", "user"]
    assert msgs[0]["content"].startswith("[Summary]")
    assert msgs[1]["content"] == "q2"
