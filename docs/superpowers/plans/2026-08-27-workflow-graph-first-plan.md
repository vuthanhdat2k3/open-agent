# Implementation plan: graph-first workflow execution

Spec: `docs/superpowers/specs/2026-08-27-workflow-graph-first-design.md`

## Phase 1 — schema and durable run identity

1. Add a graph snapshot/version/hash and trigger identity to `WorkflowRun`.
2. Add a rebuildable scheduler-trigger projection keyed by workflow and node.
3. Add migration constraints/indexes for tenant isolation and scheduled-run dedupe.
4. Keep old installation/occurrence columns compatible during transition.

Verification: migration upgrade/downgrade checks and model tests.

## Phase 2 — graph validation and service contracts

1. Extend workflow schemas/service validation with node-level errors.
2. Validate node IDs, edges, reachable triggers, cycle rules, scheduler config,
   integration references and agent/tool/sub-workflow references.
3. Compute canonical graph hash and extract scheduler trigger definitions.
4. Make create/update return trigger status and validation details.

Verification: valid manual, scheduled, event, mixed-trigger and invalid graphs.

## Phase 3 — engine trigger-scoped snapshot execution

1. Snapshot the graph when creating a run.
2. Pass `trigger_node_id` and `trigger_type` through inline, queued, webhook,
   replay and approval-resume paths.
3. Traverse only nodes reachable downstream from the selected trigger.
4. Preserve snapshot/checkpoint behavior for retries, crashes and approvals.
5. Keep manual input behavior compatible with existing `/workflows` UI.

Verification: multi-trigger branch isolation, snapshot immutability, approval
resume, replay and existing workflow engine regressions.

## Phase 4 — scheduler projection and worker

1. Reconcile scheduler nodes from every workflow graph into the projection.
2. Rebuild projection on graph changes and periodically from scratch.
3. Claim due triggers with a lease and create idempotent `WorkflowRun` rows.
4. Support hourly, daily, weekly, cron and IANA timezone calculations.
5. Disable stale projections when a scheduler node is removed or changed.
6. Keep one broken workflow/node from stopping the scheduler tick globally.

Verification: one/multiple scheduler nodes, pause/enable, edits, missed ticks,
duplicate workers and timezone boundaries.

## Phase 5 — remove catalog runtime coupling and migrate existing data

1. Route worker execution exclusively through the generic graph engine.
2. Remove the `execute_catalog_report` dispatch path after equivalent graph
   nodes are verified.
3. Add an idempotent migration that materializes the seven legacy workflows
   only when their graph is empty.
4. Preserve IDs, owners, installations, schedules and run history.
5. Build scheduler projections from the migrated scheduler nodes.
6. Keep catalog templates as graph-copy sources only.

Verification: migration dry-run/report, rerun idempotency, no overwrite of an
edited graph, and catalog-created workflow independence.

## Phase 6 — integration and permissions

1. Ensure integration node config resolves connections by org and owner.
2. Validate connection state at save/run time without storing credentials in
   graph JSON.
3. Verify webhook/event trigger identity, tenant checks and token checks.
4. Preserve RBAC for user-owned workflows and org admin/operator workflows.

Verification: Gmail/Calendar/Drive/MCP option resolution, disconnected and
cross-tenant connections, webhook rejection and permission matrix.

## Phase 7 — frontend workflow surface

1. Add scheduler config and per-trigger status to `/workflows`.
2. Add integration/connection configuration using dynamic node options.
3. Support creating from catalog by copying graph, then editing freely.
4. Show missing-trigger, invalid-node, connection and disabled-schedule states.
5. Support pause/enable for each scheduler node and trigger-aware run history.
6. Add Vietnamese and English dictionary entries for all new UI strings.

Verification: frontend tests plus `npm run typecheck && npm run build`.

## Final verification and rollout

1. Run focused backend workflow tests.
2. Run backend full test suite and record unrelated baseline failures.
3. Run frontend lint/typecheck/test/build.
4. Test migration against a backup copy before applying to the live database.
5. Deploy to a non-production environment, verify manual/scheduled/event runs,
   then promote.

## Guardrails

- Do not edit the main `dev` worktree.
- Do not overwrite non-empty user graphs during migration.
- Do not store credentials in graph snapshots.
- Do not remove catalog tables or historical run data in this change.
- Do not allow a catalog executor fallback after graph execution is enabled.
