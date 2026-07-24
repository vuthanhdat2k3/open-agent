# M11 - Evaluation And Quality Gates

## Branch

`agentos-v2/m11-evaluation-gates`

## Depends On

M10. Every evaluation run targets an immutable `AgentRelease`.

## Goal

Provide repeatable, tenant-scoped quality experiments that can block a release
when correctness, safety, latency, or cost regresses.

## Data Model

- `EvaluationSuite`: name, description, agent_id, dataset_version, timestamps.
- `EvaluationCase`: suite_id, input, expected_output, expected_tools,
  forbidden_patterns, metadata, ordinal.
- `EvaluationRun`: suite_id, agent_release_id, status, aggregate metrics,
  baseline_run_id, started_at, completed_at, triggered_by.
- `EvaluationResult`: run_id, case_id, output, observed_tools, latency_ms,
  cost_usd, score, passed, grader_details, error.

All tables include `org_id`; dataset mutations increment `dataset_version`.

## Graders

The production-safe initial set is deterministic:

- exact match after whitespace normalization
- required substring / forbidden regex with a bounded execution timeout
- required tool calls
- maximum latency and maximum cost
- aggregate pass rate

The grader interface is extensible, but an LLM judge is out of scope for M11.

## API And CLI

- CRUD `/api/evaluations/suites` and append-only nested cases.
- `POST /api/evaluations/suites/{id}/runs`
- `GET /api/evaluations/runs/{id}`
- `GET /api/evaluations/runs/{id}/results`
- `GET /api/evaluations/runs/{id}/compare/{baseline_id}`
- CLI: `python -m app.evals.cli --org <id> --suite <id> --release <id>
  --min-pass-rate 0.95`

The CLI exits non-zero when the gate fails, making the same evaluator usable in
CI. The executor is dependency-injected so tests use a deterministic fake
agent without external provider credentials.

## Acceptance Criteria

- A suite run freezes dataset version and target release.
- Re-running against the same fake executor is deterministic.
- Partial failures produce result rows and a completed run, not lost progress.
- Baseline comparison reports pass-rate, latency, and cost deltas.
- CI command returns `0` for a passing gate and non-zero for regression/error.
- Cross-tenant access is impossible at repository and route layers.
- Unit, integration, API E2E, browser E2E, and full regression suites pass.

## CI

- Add deterministic evaluation smoke data generated during the test job.
- Run the CLI quality gate against the fake executor in backend CI.
- Keep external model evaluation opt-in and credential-gated.
