# Integrations Agent Management Test Cases

## Common setup

- Use a dedicated Google test account and test organization.
- Connect Gmail with `gmail.modify`, `gmail.compose`, and `gmail.send` scopes.
- Connect Google Drive and Google Calendar for the same user.
- Capture UI chat events, approval status, provider HTTP status, and audit records.
- Every mutating case must verify that no provider request happens before approval.

## Email

| ID | Scenario | Expected result |
|---|---|---|
| E-01 | Search Gmail by `from`, subject, label, and date query | Matching messages are returned; no approval required. |
| E-02 | Open a message by provider message ID | Sender, subject, body, and metadata are returned; no mutation occurs. |
| E-03 | List Gmail labels | Labels are returned; no approval required. |
| E-04 | Create a draft | Inline approval appears; draft is created only after approval. |
| E-05 | Send a draft | Inline approval appears; Gmail send returns a send ID; retry with the same idempotency key does not duplicate. |
| E-06 | Mark read/unread | Approval is required; Gmail label state changes after approval. |
| E-07 | Star/unstar | Approval is required; `STARRED` is added/removed after approval. |
| E-08 | Archive | Approval is required; `INBOX` is removed after approval. |
| E-09 | Move to Trash | Approval is required; message moves to Trash, never permanent delete. |
| E-10 | Restore from Trash | Approval is required; message is restored. |
| E-11 | Apply/remove label | Approval is required; only requested labels change. |
| E-12 | Reply/forward | Approval creates the correct draft with thread/forward context. |
| E-13 | Reject any mutating email action | Provider is not called; chat shows rejected and run terminates cleanly. |
| E-14 | Expired or already-decided approval | No duplicate provider action; clear terminal status is shown. |
| E-15 | Missing/expired OAuth token | User-friendly reconnect error; no silent retry loop. |

## Drive

| ID | Scenario | Expected result |
|---|---|---|
| D-01 | List files with a query | Matching files are returned without approval. |
| D-02 | Read a text-exportable file | File content is returned with the configured size limit. |
| D-03 | Create a file | Approval precedes provider create request. |
| D-04 | Update file content/name | Approval precedes provider update request and only requested fields change. |
| D-05 | Delete a file | Approval precedes delete; provider result is audited. |
| D-06 | Reject create/update/delete | No Drive mutation occurs. |
| D-07 | Unsupported binary export | Clear unsupported-format error; no data corruption. |

## Calendar

| ID | Scenario | Expected result |
|---|---|---|
| C-01 | List events in a time range | Events are returned in chronological order without approval. |
| C-02 | Read one event | Event details and attendees are returned. |
| C-03 | Create event with attendees | Approval precedes create; event ID is returned. |
| C-04 | Update event | Approval precedes update; only requested fields change. |
| C-05 | Delete event | Approval precedes deletion and audit record is written. |
| C-06 | Reject create/update/delete | No Calendar mutation occurs. |
| C-07 | Invalid time range or attendee | Validation error before provider call. |

## Cross-cutting production checks

| ID | Scenario | Expected result |
|---|---|---|
| X-01 | Inline approval from the same chat | Approve/Reject is visible in the message thread; no page navigation is required. |
| X-02 | Approval page decision | Chat reconciles to the final approval state. |
| X-03 | Duplicate approval click | Operation remains idempotent and does not execute twice. |
| X-04 | Provider 401/403/429/5xx | Normalized error, audit entry, and safe retry behavior. |
| X-05 | Tool argument redaction | Tokens and secrets never appear in chat, logs, or approval snapshots. |
| X-06 | Tenant/user isolation | A user cannot access another user's connected account or provider object. |
| X-07 | Refresh/reconnect OAuth | New scopes are applied and existing connected state is handled clearly. |
| X-08 | Audit and metrics | Tool call, approval, provider result, latency, and failure status are recorded. |
