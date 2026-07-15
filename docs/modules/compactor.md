# Module: Compactor

## Purpose
Keep sessions within a model's **context window** without losing the important
parts. Used automatically by chat (and reusable by long workflow agent runs).

## Trigger
In `chat_service` (and `agent_loop` guard): if
`total_tokens(session) > 0.8 * agent.model.context_window` → compact before the
next LLM call.

## Strategy (block-aware, simplified from OpenFang)
1. **Anchor**: keep the `system` prompt and the **first** user message (the
   original task/intent).
2. **Summarize the middle**: collect the middle turns (everything between the
   anchor and the most recent `N`) and call a **cheap/fast** model
   (`tier == "fast"`) to produce a concise summary message.
3. **Keep recent**: keep the last `N` messages (default 20) verbatim so the
   agent retains immediate context.
4. **Store**: replace the live message list with
   `[system, first_user, summary, ...recent]`. The **original** history is
   archived (not deleted) so `debug` can still show it (`meta.compacted=true`).

## Data Model Impact
- `messages.meta.compacted` flag marks which rows belong to a compacted snapshot.
- Original rows remain in `messages` (archived by a `snapshot_id` or simply
  flagged) — debug reads full history; the agent loop loads the compacted view.

## API
No dedicated endpoint. Invoked internally by `chat_service` and exposed via
`debug` (you can see `compacted` markers). A future `POST /api/sessions/{id}/compact`
could trigger it manually.

## Layers
- `core/compactor.py` — pure function:
  `compact(messages, model, llm_client, keep_recent=N) -> list[Message]`.
- `services/chat_service.py` — decides when to call it.
- `repositories/session_repo.py` — load/store snapshots.

## Frontend
- No UI strictly required. The chat window simply shows a shorter history after
  compaction; `debug` reveals `compacted` markers.
- Optional: a "Compact now" button on a session (calls a future manual endpoint)
  and a small "∑ summarized" badge in the thread.

## Notes
- Cheap model for summarization avoids wasting the main agent's (expensive) tokens.
- Block-aware: it works on structured `tool_calls`/`tool_result` pairs, not just
  raw text, so tool context isn't silently dropped.
- Tunable via `keep_recent` and the `0.8` threshold constant.
