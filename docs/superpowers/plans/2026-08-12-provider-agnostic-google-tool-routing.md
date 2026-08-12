# Provider-Agnostic Google Tool Routing Implementation Plan

**Goal:** Deterministically select clear Email, Drive, and Calendar worker tools through the shared tool-choice contract, independent of the configured LLM provider.

## 1. Shared worker routing

- Add a pure worker-routing helper in `backend/app/core/agent_loop.py`.
- Match explicit English and Vietnamese resource/action phrases to existing Google integration tool names.
- Resolve only to tools present in the current `tool_by_name` mapping.
- Return `auto` for ambiguity, conversation, unsupported intent, or unavailable tools.
- Keep existing orchestrator delegate routing unchanged.
- Pass the selected choice to every agent kind on iteration zero and `auto` afterward.
- Add a connected-data directive containing the current UTC timestamp and tool-first behavior.

## 2. Google tool contracts

- Improve Email, Drive, and Calendar `ToolSpec.description` values in `backend/app/customer_intelligence/tools.py`.
- Add concise property descriptions and format guidance in `backend/app/customer_intelligence/contracts.py`.
- Document Gmail search operators, Drive filename-substring behavior, provider IDs, ISO-8601 timestamps, timezone expectations, and write inputs.
- Preserve schemas' bounds, required fields, risk tiers, and approval behavior.

## 3. Tests

- Extend agent-loop tests with worker routing cases for Email, Drive, and Calendar in English and Vietnamese.
- Cover ambiguous intent and missing-tool fallback.
- Verify a worker receives forced choice only on its first iteration.
- Preserve and run Gemini and Anthropic payload mapping tests.
- Add assertions for improved schema descriptions and provider-compatible schema conversion where useful.

## 4. Verification

- Run `ruff check app tests`.
- Run targeted driver, orchestration, task delegation, approval, and customer intelligence tests.
- Run the backend regression suite with Langfuse disabled.
- Run frontend typecheck and lint.
- Rebuild and recreate API and worker containers.
- Run sanitized runtime provider smoke tests.
- Use Playwright as `user@openagent.com`, select Gemini 2.5 Flash-Lite, and send `tìm các mail trong hôm nay`.
- Confirm both `delegate_to_email_intelligence` and `email_search` execute and the final answer is based on the tool result.

## 5. Delivery

- Review the exact diff and run `git diff --check`.
- Commit implementation and tests with scoped paths.
- Push `feat/delegated-approval-fix` normally.
- Do not force-push or merge PR #46.
