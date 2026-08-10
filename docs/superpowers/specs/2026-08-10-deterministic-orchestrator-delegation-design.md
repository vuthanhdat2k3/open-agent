# Deterministic orchestrator delegation

## Status

Implemented and verified.

## Root cause

The user-facing Assistant exposed one generic `call_agent` function and a free-form roster containing worker UUIDs. The model had to copy an opaque UUID from prose, so it could answer directly instead of delegating a Gmail/Calendar/Drive action.

## Fix approach

- Build one dynamic `delegate_to_<agent_slug>` tool per sibling agent on every orchestrator turn. Each tool binds its target agent ID in a closure and reuses the existing `call_agent` execution path.
- Infer capability tags from tool-name prefixes and the agent name, without a schema migration. New agents join the routing index automatically when their tools follow the existing `domain_action` convention.
- Match the current user message with a small, extensible synonym map. If exactly one candidate agent matches, force that named delegate tool through OpenAI-compatible `tool_choice` and add a matching system directive. Ambiguous or unmatched requests retain `auto` behavior.
- Keep the original `call_agent` tool and roster text for compatibility and context. Side-effecting worker tools remain approval-gated.

## Verification checklist

- [x] LLM complete/stream accept optional `tool_choice` while preserving default `auto`.
- [x] Unit coverage for capability inference and ambiguous routing.
- [x] Integration coverage proving a Vietnamese Gmail request forces the named email delegate.
- [x] Existing orchestrator delegation tests pass.
- [ ] Live chat verification: Gmail request creates an approval, then sends after approval.
