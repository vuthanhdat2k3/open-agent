# Provider-Agnostic Google Tool Routing Design

**Date:** 2026-08-12  
**Status:** Approved for implementation planning

## Problem

The orchestrator can deterministically delegate an email, Drive, or Calendar request, but the delegated worker still decides on its own whether to call one of its tools. A worker using Gemini 2.5 Flash-Lite received all 19 email tool schemas for `tìm các mail trong hôm nay` and returned text without calling `email_search`.

This is not a Gmail connectivity or authorization failure. The current agent loop only sends forced `tool_choice` for orchestrator agents. Tool descriptions and property schemas also omit enough usage guidance that smaller models may infer nonexistent limitations, especially for relative dates and provider query syntax.

## Goals

- Select an unambiguous Google integration tool before invoking the LLM.
- Keep selection behavior identical across OpenAI-compatible, Gemini, and Anthropic providers.
- Preserve provider-specific payload translation inside provider adapters.
- Improve Email, Drive, and Calendar schemas and descriptions so models generate valid arguments.
- Keep approval requirements unchanged for write and dangerous operations.
- Preserve `auto` selection for ambiguous, conversational, or unsupported requests.

## Non-Goals

- Auditing filesystem, shell, memory, web, sandbox, or arbitrary MCP tool descriptions.
- Replacing the agent loop with a separate classifier model.
- Executing tools without an LLM-generated argument object.
- Bypassing approval gates for write or dangerous tools.
- Guaranteeing intent recognition for unrestricted natural language.

## Considered Approaches

### Prompt and schema improvements only

This is the smallest change but cannot guarantee a tool call. Models remain free to answer directly even when current data is required.

### Force any available worker tool

This guarantees a call but does not guarantee the correct tool. It is unsafe for workers that expose both read and write operations.

### Deterministic tool selection with improved schemas

This is the selected approach. The agent loop maps clear integration intents to an existing `ToolSpec`, expresses the selection in the shared OpenAI-style `tool_choice` contract, and lets each provider adapter translate that contract to its native payload.

## Architecture

### Shared selection contract

Add a pure routing helper in the agent-loop layer. It receives the current user instruction and the worker's actual `tool_by_name` mapping. It returns either:

```python
{"type": "function", "function": {"name": "email_search"}}
```

or `"auto"` when the request is not safely resolvable to one tool.

The helper may only select a name present in `tool_by_name`. This prevents stale routing rules from forcing tools that are unavailable to the current agent or filtered out during tool construction.

The same internal contract is passed to every LLM driver. Provider-specific handling remains:

- OpenAI-compatible: native function `tool_choice`.
- Gemini Generate Content: `toolConfig.functionCallingConfig` with `mode: ANY` and one `allowedFunctionNames` entry.
- Anthropic Messages: `tool_choice: {"type": "tool", "name": ...}`.

### Worker routing

Deterministic worker routing applies to agents whose available tools include the corresponding Google integration family. It is based on explicit action and resource terms, not on agent names.

Initial intent map:

| Resource | Intent | Tool |
|---|---|---|
| Email | search, find, filter, mail for a date/range | `email_search` |
| Email | list inbox or new mail | `email_list_new` |
| Email | read a message identified by provider ID | `email_get` |
| Email | draft, reply, forward, send, label, archive, star, trash, restore | Matching `email_*` tool |
| Drive | search or list files | `drive_list_files` |
| Drive | read a file identified by file ID | `drive_get_file` |
| Drive | create, update, or delete a file | Matching `drive_*` tool |
| Calendar | search or list events in a time range | `calendar_list_events` |
| Calendar | read an event identified by provider ID | `calendar_get_event` |
| Calendar | create, update, or delete an event | Matching `calendar_*` tool |

English and Vietnamese terms are supported. Specific action terms take precedence over generic resource terms. If multiple different tools remain plausible, selection stays `auto`.

The selected tool is forced only for the first model iteration. Later iterations use `auto` so the model can inspect tool results, call follow-up tools when useful, and synthesize the final response.

### Orchestrator routing

Existing orchestrator delegation remains unchanged. It first selects a named delegate tool such as `delegate_to_email_intelligence`. The delegated worker then independently selects its business tool using the shared worker-routing helper.

### Tool-use directive

Workers with connected-data tools receive a concise directive:

- Use a relevant tool before answering requests that require current external data.
- Do not claim the platform cannot access a connected service without attempting the relevant read tool.
- Convert relative date phrases into provider-supported query arguments.
- Ask for clarification instead of forcing a write operation when required details or intent are ambiguous.

The directive includes the current UTC timestamp for relative-time resolution. An explicit timezone in the user's request takes precedence; when none is available, the model uses UTC and states that assumption in its answer. Gmail requests that do not require a calendar-day boundary may use relative operators such as `newer_than:1d`.

The directive supplements deterministic routing; it is not the routing mechanism.

## Schema and Description Improvements

The audit is limited to registered Email, Drive, and Calendar tools.

### Email

- Explain that `email_search.query` accepts Gmail search syntax.
- Include compact examples such as `newer_than:1d`, `after:2026/08/12 before:2026/08/13`, `from:alice@example.com`, `subject:invoice`, and `has:attachment`.
- State that natural-language relative dates must be converted before calling the tool.
- Distinguish inbox listing (`email_list_new`) from arbitrary search (`email_search`).
- Describe provider message IDs consistently on get/state/reply/forward operations.
- Clarify that draft creation and sending are separate operations.

### Drive

- State that `drive_list_files.query` is an optional case-insensitive filename substring. The MCP implementation excludes trashed files and returns matches ordered by most recently modified; it does not accept raw Drive query syntax.
- Distinguish listing/searching metadata from reading file content.
- Describe file IDs, content limits, and write inputs consistently.

### Calendar

- Require ISO-8601 timestamps with explicit timezone offsets for time ranges and event writes.
- Explain how relative phrases such as today or tomorrow must be resolved before invocation.
- Distinguish list/search by time range from get-by-provider-ID.
- Describe attendees, location, and mutable fields consistently.

Descriptions must state capability and argument expectations without duplicating approval policy already enforced by `ToolSpec` metadata.

## Safety and Error Handling

- A routing rule cannot select a tool missing from the current agent's tool map.
- Ambiguous intent remains `auto`; no arbitrary fallback tool is forced.
- Existing risk-tier checks and approval gates execute after selection and remain authoritative.
- Invalid or incomplete model-generated arguments continue through existing schema validation and tool error handling.
- If a connected account is missing or expired, the selected tool returns the existing explicit connection error; the model must report that result rather than inventing an access limitation.

## Testing

### Unit tests

- English and Vietnamese intent mapping for every Email, Drive, and Calendar operation group.
- Date-oriented email requests select `email_search`.
- Calendar time-range requests select `calendar_list_events`.
- Generic Drive search selects `drive_list_files`.
- Ambiguous and conversational requests remain `auto`.
- Rules never select tools absent from `tool_by_name`.
- Only the first worker iteration receives the forced choice.
- Improved schema descriptions survive OpenAI, Gemini, and Anthropic schema conversion.

### Provider contract tests

- OpenAI-compatible requests receive the shared function choice unchanged.
- Gemini payloads contain `mode: ANY` and exactly one allowed function.
- Anthropic payloads contain the matching native named-tool choice.
- `auto` behavior remains unchanged for all providers.

### Regression and runtime tests

- Run targeted agent-loop, driver, Google integration, delegation, and approval tests.
- Run the full backend suite and frontend typecheck/lint.
- Rebuild and recreate API and worker containers.
- Runtime smoke each configured native provider without logging credentials.
- Use Playwright with the user account to send `tìm các mail trong hôm nay` through Assistant using Gemini.
- Verify both tool calls occur: `delegate_to_email_intelligence`, then `email_search`.
- Verify the final answer contains Gmail search results or an explicit tool-level result such as no matching email, not a fabricated inability to search by date.

## Rollout

The change applies to new turns after API and worker deployment. Existing incorrect chat messages are retained as historical records and are not rewritten.
