# KNOWN ISSUE: Workflow parallel nodes share one AsyncSession (race condition)

Date found: 2026-08-10
Status: **Fixed and live-verified**.

## Symptom

When a workflow's graph has 2+ nodes that become ready to run at the same
time (a fan-out, e.g. one node's output feeds two downstream nodes that
don't depend on each other), one of the concurrent nodes intermittently
fails with:

```
This session is provisioning a new connection; concurrent operations are
not permitted
```

Reproduced live against the real `research-report` workflow
(`64ba8f36-8c5c-4dfa-93b6-973d32b7337e`, also present in
`ee97ad65-9641-451b-a26a-73f70af3d4cf`): graph is
`plan → {research, fact_check} → merge → write → output`. `research` and
`fact_check` both become ready as soon as `plan` finishes and run
concurrently. In the reproduction run, `fact_check` failed with the error
above while `research` succeeded; `merge`/`write` still completed using
only `research`'s output (the engine tolerates a failed parallel branch and
continues), so the workflow *finishes* but silently loses one branch's
work.

## Root cause

`backend/app/core/workflow/engine.py` (~line 459-461):

```python
tasks[n["id"]] = asyncio.create_task(run_node(n))
...
results = await asyncio.gather(*tasks.values(), return_exceptions=True)
```

Every ready node's `run_node(n)` closure captures and uses the **same**
`db: AsyncSession` instance passed into the outer `run_workflow`/engine
call. SQLAlchemy's `AsyncSession` is not safe for concurrent use by
multiple coroutines - only one logical operation may be in flight on a
given session at a time. When two `asyncio.create_task`-wrapped node runs
both try to use `db` at the same moment (each doing its own
selects/commits, and "agent" nodes additionally call the full
`run_agent_loop` which does many DB reads/writes), the session's internal
connection-provisioning state gets corrupted for whichever one loses the
race, raising the "concurrent operations are not permitted" error from
asyncpg/SQLAlchemy.

This is a distinct bug from the message-drop bug fixed on 2026-08-10 (see
`2026-08-10-multiagent-orchestration.md` §3) - that one silently dropped
the instruction text; this one is a genuine session-concurrency crash, and
only manifests when a workflow graph actually has parallel branches (most
workflows tested so far in this session happened to be linear chains,
which is why this wasn't caught earlier).

## Blast radius

Any workflow with a fan-out (two or more nodes with no dependency between
them, ready at the same time) is affected - not limited to "agent" kind
nodes; "tool" nodes and any other node kind that touches `db` inside
`run_node` would hit the same race. Linear (fully sequential) workflows are
unaffected, which is presumably why this has gone unnoticed.

## Suggested fix approach (not implemented)

Give each concurrently-dispatched node its own `AsyncSession` instead of
sharing the outer one - e.g. open a fresh session (from the same
sessionmaker/engine) inside each `asyncio.create_task`-wrapped node
execution, commit/close it within that task, and only use the outer `db`
for pre/post fan-out bookkeeping that isn't itself concurrent. Needs care
around:
- `node_run` row updates (currently written via the shared `db`) - each
  parallel branch's writes need to go through its own session too, then
  the outer orchestration needs to see committed state (re-query via the
  outer `db`, or refresh/merge objects across sessions).
- Any object passed into `run_node` that was loaded via the outer `db`
  session (e.g. `workflow`, `workflow_run`) may need re-fetching or
  detaching before being touched from a different session, to avoid
  SQLAlchemy's "object already attached to another session" errors.
- Add a regression test with an actual fan-out graph (2 parallel "tool" or
  stub nodes hitting the DB) asserting both branches complete successfully
  under `asyncio.gather`, not just a linear chain.

## Verification checklist for the fix

- [x] Both `research` and `fact_check` (or an equivalent stub reproduction)
      complete successfully when run concurrently, no
      "concurrent operations are not permitted" error.
- [x] Re-run the existing `research-report` workflow live end-to-end,
      confirm `fact_check`'s real output makes it into `merge`'s combined
      input (currently silently dropped).
- [x] New unit/integration test simulating a fan-out graph against a real
      (SQLite) DB with concurrent node execution.
- [x] Full backend test suite still green.

Verification on 2026-08-10:

- Regression: `test_parallel_tool_nodes_use_independent_db_sessions` forces
  two parallel tool nodes through a barrier, performs a real database write
  from each node, and confirms both outputs reach the merge node.
- Workflow regression group: 22 passed.
- Full backend suite: 243 passed, 4 pre-existing deprecation warnings.
- Live LLM/database run: `423395a4-6073-4820-b1d2-4bc3fac03757` completed
  with every node succeeded and no error events. The merge input contained
  both `research` (6,271 characters) and `fact_check` (4,090 characters).
