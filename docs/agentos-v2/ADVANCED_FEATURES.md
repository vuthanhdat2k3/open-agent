# AgentOS v2 - Advanced Production Features

## Purpose

M0-M9 establish a multi-tenant agent runtime with authentication, guardrails,
durable workflows, observability, deployment, and a usable frontend. The next
production gap is controlled change: teams need to release agent configuration
safely, prove quality before promotion, and protect shared infrastructure from
noisy or unexpectedly expensive tenants.

This roadmap selects three features that form one release-safety loop:

1. **M10 Agent Releases** - immutable configuration revisions, explicit
   publish/rollback, and release audit history.
2. **M11 Evaluation and Quality Gates** - versioned test sets, repeatable
   experiments, deterministic graders, baseline comparison, and a CI exit code.
3. **M12 Tenant Quotas and Admission Control** - request rate, concurrent-run,
   and monthly-cost limits with Redis-backed distributed enforcement.

Each milestone has its own branch, migration, tests, review, and push. Merge
order is M10 -> M11 -> M12 because evaluations target immutable agent releases.

## Industry References

The scope is based on capabilities used by mature agent platforms:

- LangSmith manages immutable prompt commits, named staging/production
  environments, promotion, and rollback:
  https://docs.langchain.com/langsmith/manage-prompts
- LangSmith evaluates multiple experiments against versioned datasets and
  compares quality, latency, token usage, models, prompts, and tools:
  https://docs.langchain.com/langsmith/evaluate-llm-application
  https://docs.langchain.com/langsmith/manage-datasets
- Microsoft Copilot Studio provides repeatable test sets, agent-version
  selection, detailed transcripts, activity maps, and side-by-side version
  comparison:
  https://learn.microsoft.com/en-us/microsoft-copilot-studio/agents-experience/analytics-agent-evaluation-intro
  https://learn.microsoft.com/en-us/microsoft-copilot-studio/analytics-agent-evaluation-results
- OpenAI Agents SDK persists resumable run state for long-running approvals and
  includes guardrails, sessions, and tracing:
  https://openai.github.io/openai-agents-python/
  https://openai.github.io/openai-agents-python/human_in_the_loop/
- LangGraph checkpoint replay/fork demonstrates why a production execution
  must retain the exact configuration version used by a run:
  https://docs.langchain.com/oss/python/langgraph/use-time-travel

## Product Principles

- **Immutable evidence**: a completed run points to an immutable agent release.
- **No implicit production mutation**: editing a draft does not change the
  active runtime configuration.
- **Deterministic core**: quality gates include graders that do not require
  another LLM and can run in CI without provider credentials.
- **Tenant isolation first**: every new table contains `org_id`; every lookup is
  tenant-scoped.
- **Distributed enforcement**: limits must remain correct with multiple API and
  worker replicas.
- **Fail deliberately**: quota backend failure policy is explicit; mutation/run
  admission fails closed while read-only endpoints remain available.
- **Backward compatibility**: existing agent CRUD and chat clients continue to
  work during rollout.

## Git And Merge Plan

| Milestone | Branch | Parent | Pull request base |
|---|---|---|---|
| Docs | `docs/advanced-production-roadmap` | `bugfix/fullstack-e2e` | bugfix branch |
| M10 | `agentos-v2/m10-agent-releases` | docs branch | docs branch |
| M11 | `agentos-v2/m11-evaluation-gates` | M10 | M10 |
| M12 | `agentos-v2/m12-tenant-quotas` | M11 | M11 |

After the bugfix and docs PRs merge, feature PR bases can be retargeted in
order. No feature branch is merged while its CI is red.

## Deferred Candidates

These are valuable but intentionally excluded from this implementation batch:

- Signed outbound webhooks with durable retry and dead-letter queues.
- Percentage/canary traffic splitting between releases.
- Online LLM-as-a-judge evaluation over sampled production traces.
- SCIM/SAML enterprise provisioning.
- Multi-region active-active execution.

They should be reconsidered after M12 metrics show actual integration,
evaluation, and scaling demand.

