# Gmail Monitor Workflow

## Goal

Refactor the existing Gmail detection pipeline into a first-class workflow in the Automation Hub without creating a second email-processing implementation.

The existing Gmail webhook, reconciliation, history sync, deduplication, guard, classification, routing, research, approval, and calendar execution services remain the canonical implementation. The workflow controls whether the post-ingest automation is active.

## User experience

The catalog exposes one template:

- `gmail_monitor_and_triage`
- Name: Monitor and triage new Gmail
- Trigger: new Gmail event
- Default behavior: analyze new email, classify it, ignore spam, notify for normal mail, research customer mail, and create a calendar proposal when meeting intent is detected.
- External side effects remain approval-gated unless an existing trusted rule is valid.

The workflow uses the existing Automation Hub setup, Active, pause/resume, Run now, and Activity surfaces. It is not configured as a technical scheduler-only job.

## Lifecycle and cutover

1. Gmail webhook/reconciliation receives a notification.
2. History sync persists and deduplicates inbound messages and advances the Gmail checkpoint.
3. The connection's Gmail monitor installation is resolved by `(org_id, owner_user_id, template_key)`.
4. If the installation is enabled, the existing classification outbox event is created.
5. If it is paused or absent, the email remains ingested and marked `monitoring_paused`; no LLM, report, notification, research, or calendar action is created.
6. Enabling the workflow establishes a cutover checkpoint at the current Gmail history boundary. Only messages after that boundary are eligible for automatic analysis.

The first installation for an already connected account must not replay historical mail. Existing clean-cutover/checkpoint logic is reused; no full mailbox scan is allowed on server restart.

## Cost and latency controls

- Webhook remains hot-path only: verify, persist event, return success.
- Classification remains asynchronous through the existing outbox and queue.
- Duplicate messages are suppressed before LLM work.
- Spam and low-value messages can be stopped by the existing classifier/policy result; no research branch is created for them.
- Provider and LLM rate limits remain in their existing worker queues.
- Paused installations still perform only provider sync/checkpoint work.

## Data and safety invariants

- Email body is untrusted data and never becomes an instruction.
- Disabled monitoring never deletes email or rewinds the Gmail checkpoint.
- No report is created without a valid classified route.
- A single inbound message can create at most one classification request per content hash.
- Calendar creation still requires explicit approval or a valid trusted rule.
- Installation ownership and organization scope are verified server-side.

## API and model changes

- Add the Gmail monitor template to the catalog seed.
- Add an installation binding/cutover checkpoint for Gmail connections.
- Route Gmail classification requests only when an enabled installation exists.
- Expose installation status and cutover timestamp in the Active view.
- Keep existing sync and classification endpoints backward compatible for the migration period.

## Testing and rollout

- Unit test enabled, paused, absent, and cutover behavior.
- Assert paused mode advances checkpoint but creates zero classification outbox events.
- Assert enabled mode creates exactly one event for a new message and deduplicates retries.
- Assert restart/reconciliation never reprocesses pre-cutover messages.
- Add API/UI tests for enable, pause, resume, and cutover status.
- Roll out in shadow mode first, then enable for an allowlist of connected accounts.

