"""Surface projection: derive the provider-visible message history from
the append-only session event log.

The log is the source of truth ("model-visible means logged"); this module
folds events into OpenAI wire-format messages. Compaction shadows old ranges
via replace surface ops instead of deleting anything, and crash-orphaned
tool calls are synthesized deterministic results so providers never see a
dangling ``tool_calls`` turn.
"""

from __future__ import annotations

from typing import Any

from app.core import session_log as slog
from app.models.session_event import SessionEvent

# Deterministic model-facing text for a tool call whose run crashed before a
# result was recorded (mirrors dsh's interruptedTurnClosers guidance style).
_INTERRUPTED_TOOL_RESULT = (
    "error: tool execution was interrupted before a result was recorded. "
    "If you retry this action, first verify whether it already took effect."
)


def _shadowed(seq: int, shadow_ranges: list[tuple[int, int]]) -> bool:
    return any(start <= seq <= end for start, end in shadow_ranges)


def _synthesize_repair_node(call_data: dict[str, Any], call_seq: int) -> dict[str, Any]:
    """Build an in-memory-only repair node - never written to the log."""
    return {
        "seq": None,
        "type": slog.TOOL_RESULT,
        "data": {
            "content": _INTERRUPTED_TOOL_RESULT,
            "tool_call_id": str(call_data.get("tool_call_id") or ""),
            "repair_for_seq": call_seq,
        },
    }


def derive_messages(
    events: list[SessionEvent],
    *,
    repair_crash_tail: bool = True,
) -> list[dict[str, Any]]:
    """Fold session events into OpenAI-format provider messages.

    - Only surface-eligible types participate; everything else is ignored.
    - A replace surface op shadows its cited range and lands a summary node
      where the range started.
    - Tool calls attach to the preceding assistant message as OpenAI
      ``tool_calls``; their results follow as ``role:"tool"`` messages -
      full fidelity across turns.
    - Crash-tail repair: an un-resulted trailing ``tool/call`` gets a
      synthetic error result (in-memory only) so the request stays valid.
    """
    if not events:
        return []

    # Pass 1: collect shadow ranges from compaction summaries.
    shadow_ranges: list[tuple[int, int]] = []
    summary_nodes_by_start: dict[int, SessionEvent] = {}
    for ev in events:
        if ev.type != slog.COMPACTION_SUMMARY:
            continue
        op_ = ev.data.get("surface_op") or {}
        start_seq = op_.get("start_seq")
        end_seq = op_.get("end_seq")
        if isinstance(start_seq, int) and isinstance(end_seq, int):
            shadow_ranges.append((start_seq, end_seq))
            summary_nodes_by_start[start_seq] = ev
    shadow_ranges.sort()

    # Pass 2: index tool results by call id for pairing/repair.
    result_by_call_id: dict[str, SessionEvent] = {}
    for ev in events:
        if ev.type == slog.TOOL_RESULT and not isinstance(ev.data.get("surface_op"), dict):
            call_id = str(ev.data.get("tool_call_id") or "")
            if call_id:
                result_by_call_id[call_id] = ev

    # Pass 3: fold visible nodes in seq order.
    nodes: list[dict[str, Any]] = []

    def attach_call(ev: SessionEvent) -> None:
        """Attach a tool/call to the most recent assistant node, or mint a
        minimal assistant turn when none exists (well-formed pairing)."""
        call = {
            "id": str(ev.data.get("tool_call_id") or ""),
            "type": "function",
            "function": {"name": ev.data.get("name"), "arguments": ev.data.get("arguments") or "{}"},
        }
        if nodes and nodes[-1]["msg"]["role"] == "assistant":
            existing = nodes[-1]["msg"].get("tool_calls")
            if existing:
                existing.append(call)
            else:
                nodes[-1]["msg"]["tool_calls"] = [call]
        else:
            nodes.append(
                {"seq": ev.seq, "msg": {"role": "assistant", "content": None, "tool_calls": [call]}}
            )
        entry = nodes[-1]
        entry.setdefault("call_ids", []).append(call["id"])

    for ev in events:
        # Land any summary node whose shadowed range starts here.
        if _shadowed(ev.seq, shadow_ranges):
            start_hit = next((s for s, _ in shadow_ranges if s == ev.seq), None)
            if start_hit is not None and ev.seq in summary_nodes_by_start:
                summary_ev = summary_nodes_by_start[start_hit]
                nodes.append(
                    {
                        "seq": summary_ev.seq,
                        "msg": {"role": "user", "content": str(summary_ev.data.get("content") or "")},
                    }
                )
            continue  # node inside a shadowed range
        if ev.type == slog.USER_MESSAGE:
            user_content = ev.data.get("content")
            if not isinstance(user_content, list):
                user_content = str(user_content or "")
            nodes.append({"seq": ev.seq, "msg": {"role": "user", "content": user_content}})
        elif ev.type == slog.ASSISTANT_MESSAGE:
            msg: dict[str, Any] = {"role": "assistant", "content": ev.data.get("content")}
            nodes.append({"seq": ev.seq, "msg": msg})
        elif ev.type == slog.TOOL_CALL:
            attach_call(ev)
        elif ev.type == slog.TOOL_RESULT:
            # Results render after their owning node; paired in pass 4.
            continue

    # Pass 4: interleave tool results right after their owning node.
    out: list[dict[str, Any]] = []
    emitted_result_seqs: set[int] = set()
    for node in nodes:
        out.append(node["msg"])
        for cid in node.get("call_ids", []):
            res_ev = result_by_call_id.get(cid)
            if res_ev is None or res_ev.seq in emitted_result_seqs:
                continue
            if _shadowed(res_ev.seq, shadow_ranges):
                continue
            out.append({"role": "tool", "tool_call_id": cid, "content": str(res_ev.data.get("content") or "")})
            emitted_result_seqs.add(res_ev.seq)

    # Crash-tail repair: any trailing call whose result never landed gets a
    # deterministic synthetic result so providers never see dangling calls.
    # When repair_crash_tail is False (e.g. active approval resume), un-resulted
    # trailing calls are left open to be satisfied by the resumed execution step.
    if repair_crash_tail:
        open_calls: dict[str, SessionEvent] = {}
        for ev in events:
            if ev.type == slog.TOOL_CALL and not _shadowed(ev.seq, shadow_ranges):
                open_calls[str(ev.data.get("tool_call_id") or "")] = ev
            elif ev.type == slog.TOOL_RESULT:
                open_calls.pop(str(ev.data.get("tool_call_id") or ""), None)
        for cid, ev in open_calls.items():
            if cid and cid not in result_by_call_id:
                out.append(_synthesized_tool_message(ev))

    return out


def _synthesized_tool_message(call_event: SessionEvent) -> dict[str, Any]:
    return {
        "role": "tool",
        "tool_call_id": str(call_event.data.get("tool_call_id") or ""),
        "content": _INTERRUPTED_TOOL_RESULT,
    }


def estimate_history_tokens(messages: list[dict[str, Any]]) -> int:
    """Cheap chars//4 estimate over message contents (matches the heuristic
    used for usage accounting elsewhere)."""
    total_chars = 0
    for m in messages:
        content = m.get("content")
        if isinstance(content, str):
            total_chars += len(content)
        tool_calls = m.get("tool_calls") or []
        for tc in tool_calls:
            fn = tc.get("function") or {}
            total_chars += len(str(fn.get("name") or "")) + len(str(fn.get("arguments") or ""))
    return total_chars // 4
