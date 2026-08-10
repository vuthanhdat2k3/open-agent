# Multi-Agent Orchestration (Chat) — Design Note

Date: 2026-08-10
Status: Implemented, live-verified (sequential + parallel + A2A + Evaluations)

## 1. Context

The 2-role RBAC design (see the prior spec) commits to: a plain `user` chats
with the org's primary (`kind=orchestrator`) agent only, which delegates to
worker agents internally. The primitives for this already existed
(`Agent.kind`, `call_agent` tool, `ORCHESTRATOR_SYSTEM_SUFFIX`) but were
unused - no agent had ever been marked `orchestrator`, the orchestrator had
no way to discover which agents it could delegate to, and the UI had no
control to set `kind` at all. This pass makes the mechanism real, using
Workflow's own graph engine was considered and rejected: Workflows are a
DAG of discrete, admin-authored runs, not a fit for open-ended multi-turn
chat - the existing agent-loop + `call_agent` primitives already integrate
naturally with Chat's session/streaming infrastructure.

## 2. Changes

- `agent_loop.py`: new `_build_orchestrator_roster(db, org_id, exclude_id)`
  lists sibling agents (id/name/description) and gets appended to the
  system prompt whenever `agent.kind == "orchestrator"` and the agent has
  the `call_agent` tool - otherwise the LLM has no way to know which raw
  agent ids exist to delegate to.
- `app/agents/page.tsx`: added the missing `kind` (worker/orchestrator)
  selector to the create/edit form - previously only settable via direct
  API calls, with no UI control at all.

## 3. Critical bug found and fixed during live verification

Live-testing the very first real delegation call surfaced a pre-existing
bug unrelated to the roster/UI work above: `agent_loop.py`'s message-building
block appended the current turn's user message **inside** `if session_id:`.
Every `call_agent` delegation (and, by the same code path, every A2A call
and workflow agent-node execution) runs with `session_id=None` - so the
actual instruction was silently never added to the LLM request. Every
delegated worker only ever saw its system prompt and replied "your message
came through empty," while the orchestrator burned through all
`max_iterations` retrying. Fixed by moving the append outside the
`session_id` guard (still respecting `approval_resume_id`).

A regression test (`test_run_agent_loop_includes_message_without_session_id`)
was added and manually verified to fail against the pre-fix code before
confirming it passes against the fix - this exact bug should never come
back silently.

## 4. Verification

- `backend/tests/test_orchestrator_delegation.py` — reusable regression
  suite, run this after any change to `agent_loop.py`'s turn/tool-call
  handling or the orchestrator directive:
  - `test_roster_lists_siblings_and_excludes_self`
  - `test_roster_empty_when_no_siblings`
  - `test_run_agent_loop_includes_message_without_session_id` (the bug guard)
  - `test_orchestrator_sequential_delegation` (2 delegate turns then synthesis)
  - `test_orchestrator_parallel_delegation` (2 call_agent calls in 1 turn)
- Full suite: 225/225 passing.
- Live end-to-end with a real LLM (not mocked), against the real database:
  created an `Assistant` orchestrator agent (tools: `call_agent`,
  `memory_recall`) in the real org via the API.
  - **Sequential**: "search the web for React Flow, then have Coder write
    an HTML snippet using that result" → orchestrator called `web-search`
    first, fed its real result into the instruction for `Coder`, and
    synthesized both into one final answer (real search result + real
    generated HTML).
  - **Parallel**: "two independent searches, do them at the same time" →
    both `call_agent` calls happened in a single turn (44.7s total vs. 83s
    for the 2-turn sequential case), both returned real distinct results,
    synthesized correctly.
  - Test chat sessions/tasks cleaned up afterward; the `Assistant`
    orchestrator agent itself was kept (the actual deliverable).
- Follow-up live verification for the two other sessionless callers:
  - **A2A**: `POST /api/a2a/tasks` ran through the real ASGI route, database,
    auth, and LLM. Task `645a51f7-cae0-4426-9be3-3360af164f0d` succeeded and
    returned the exact unique marker supplied in the A2A input. The test agent's
    temporary `a2a_exposed` flag was restored to `False` afterward.
  - **Evaluations**: live suite `c86d1241-618e-47aa-9c59-cb0ac9bfc437`, case
    `4b3bb217-b9cc-4c6f-8221-ce78a3e1072d`, and run
    `6b4a1cb2-4fec-4ac1-8bb8-6b5b75690281` exercised the real evaluation API,
    `LiveAgentExecutor`, database, and LLM. The run completed with pass rate
    `1.0`, no result error, and the exact marker from `case.input` in output.
- No caller-specific regression test was added: both A2A and Evaluations only
  forward their input to `run_agent_loop`, while
  `test_run_agent_loop_includes_message_without_session_id` directly guards the
  shared message-building root cause. Their existing route/executor tests cover
  the forwarding boundaries without duplicating that implementation test.

## 5. Not done in this pass

- No admin UI badge/indicator distinguishing orchestrator vs. worker agents
  in the Agents list cards (cosmetic, `kind` is functional but not
  visually surfaced beyond the edit form).
- Only one orchestrator agent exists; if an org configures multiple, Chat's
  `list_agents` filter (from the RBAC spec) returns all of them to a `user`
  - no "pick the default one" logic beyond what already exists.
