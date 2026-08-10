# Deterministic orchestrator delegation

## Status

Implemented and verified, including sticky routing for short follow-ups.

## Root cause

The user-facing Assistant exposed one generic `call_agent` function and a free-form roster containing worker UUIDs. The model had to copy an opaque UUID from prose, so it could answer directly instead of delegating a Gmail/Calendar/Drive action.

## Fix approach

- Build one dynamic `delegate_to_<agent_slug>` tool per sibling agent on every orchestrator turn. Each tool binds its target agent ID in a closure and reuses the existing `call_agent` execution path.
- Infer capability tags from tool-name prefixes and the agent name, without a schema migration. New agents join the routing index automatically when their tools follow the existing `domain_action` convention.
- Match the current user message with a small, extensible synonym map. If exactly one candidate agent matches, force that named delegate tool through OpenAI-compatible `tool_choice` and add a matching system directive. Ambiguous or unmatched requests retain `auto` behavior.
- Add a generic Tier 2 sticky fallback for short follow-ups such as “hãy gửi”: derive the sole recent delegated worker from the existing `Task.root_run_id` trail, with `Task.progress.session_id` as the cross-turn fallback because each new chat turn has its own root run. The lookup is bounded by a 30-minute TTL and five-task lookback. Tier 1 keyword routing always wins; ambiguous or stale trails remain `auto`.
- Deliberately do not match a broad text window from conversation history. That approach can hijack unrelated follow-ups; the Task trail provides structured delegation state without a new intent table or migration.
- Keep the original `call_agent` tool and roster text for compatibility and context. Side-effecting worker tools remain approval-gated.

## Verification checklist

- [x] LLM complete/stream accept optional `tool_choice` while preserving default `auto`.
- [x] Unit coverage for capability inference and ambiguous routing.
- [x] Integration coverage proving a Vietnamese Gmail request forces the named email delegate.
- [x] Sticky routing coverage for short follow-ups, long-message guard, Tier 1 precedence, ambiguous workers, and TTL expiry.
- [x] Full backend suite: 251 tests passed.
- [x] Existing orchestrator delegation tests pass.
- [x] Live runtime and Playwright verification: a real user Gmail request routed to `email-intelligence` and created an `email_create_draft` approval visible in the user Approvals page.
- [ ] Manual UI approval of the draft and subsequent `email_send` approval remains intentionally user-controlled; the test left this approval pending and sent no external email.
