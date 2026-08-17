# Durable Enterprise File Ingestion Design

**Date:** 2026-08-17

**Status:** Approved architecture; written specification awaiting review

**Target branch:** `dev`

**Implementation branch:** `feat/enterprise-rag-ingestion`

## 1. Summary

OpenAgent will move file ingestion out of the synchronous API request and out of each organization's user-configured MCP integrations. The backend will own a durable ingestion job, persist its state in PostgreSQL, dispatch work through the existing ARQ/Redis worker, and call rag-service over its authenticated internal REST API. Rag-service remains the owner of parsing, PDF classification, Docling OCR/PPTX conversion, chunking, embedding, and vector storage.

This boundary gives the platform one production control plane for authorization, retries, idempotency, audit history, and user-visible status while preserving rag-service as the document-processing data plane. Docling stays internal and is reachable only from rag-service. Pdf-inspector stays an in-process rag-service dependency and is never exposed as a network service.

The first implementation covers uploaded files only. URL and raw-text ingestion retain their current behavior.

## 2. Problem statement

The current Files API performs ingestion synchronously inside the request handler:

1. The backend downloads the complete object from S3/MinIO.
2. It base64-encodes the file.
3. It looks up an organization MCP server named `rag`.
4. It invokes `rag_ingest_file` through MCP.
5. It extracts a document ID from human-readable text with a regular expression.
6. It marks the upload as ingested without a durable backend job or a validated structured result.

This creates production risks:

- A new organization cannot ingest files until an administrator manually creates an internal MCP integration.
- Request lifetime is coupled to PDF classification, OCR, parsing, embedding, and vector storage.
- API or worker restarts can lose the operation or leave ambiguous state.
- Large files are expanded by base64 and held in memory more than necessary.
- Retry behavior, dead-letter state, and operational ownership are absent.
- A human-readable MCP response can produce false success or brittle document-ID extraction.
- The UI cannot distinguish queued, processing, retrying, failed, and completed work.

MCP remains appropriate for user-managed tools and third-party integrations. It is not the correct mandatory transport between first-party services in the same deployment.

## 3. Goals

1. Return promptly from the ingest API with a durable job identifier.
2. Make PostgreSQL the source of truth for job state and ARQ/Redis a replaceable delivery mechanism.
3. Guarantee organization and file authorization at job creation and status lookup.
4. Prevent duplicate active ingestion and make repeated requests idempotent.
5. Retry transient infrastructure failures with bounded exponential backoff.
6. Expose permanent failure and dead-letter states without reporting false success.
7. Stream file data from object storage to rag-service without base64 encoding.
8. Validate the structured rag-service response before marking a file ingested.
9. Persist extraction provenance and warnings needed for support and audit.
10. Preserve zero-config PDF behavior when Docling is disabled and preserve the current text-PDF fast path.
11. Keep Docling and rag-service on the internal network with service authentication.
12. Provide automated unit, integration, and real-container E2E coverage for text PDF, scanned PDF, and PPTX.

## 4. Non-goals

- Building a second queue or worker runtime inside rag-service.
- Converting all rag-service ingestion modes to asynchronous processing.
- Replacing ARQ, Redis, PostgreSQL, MinIO/S3, or the vector database.
- Exposing Docling or pdf-inspector directly to the backend, frontend, or public network.
- Removing MCP as a user-configurable integration mechanism.
- Adding XLSX or changing the existing DOCX parser.
- Reworking embedding, chunking, vector collections, or retrieval semantics.
- Providing distributed cancellation of a conversion already executing in rag-service.
- Automatically re-ingesting historical files during deployment.

## 5. Options considered

### 5.1 Selected: backend durable job plus direct internal RAG REST

The backend creates and owns the job, dispatches it through the existing worker, and calls `POST /api/v1/ingest/file` on rag-service with multipart data and `X-API-Key` authentication.

This reuses the platform's existing queue and worker, removes per-organization setup for a first-party service, and keeps one clear owner for product-facing state.

### 5.2 Rejected: backend job plus per-organization MCP invocation

This adds durability but retains the principal operational failure: every organization must correctly configure an MCP server for an internal platform capability. It also keeps base64 transport and the weak human-text result contract.

### 5.3 Rejected for this phase: a new queue inside rag-service

Rag-service could own its own queue, persistence, scheduler, workers, and job API. That can be appropriate if rag-service later becomes an independently scaled document-processing platform, but today it duplicates mature backend infrastructure and substantially increases deployment and operational scope.

## 6. Architecture and ownership

```text
Browser
  |
  | POST /api/files/{file_id}/ingest
  v
Backend API ---- transaction ----> PostgreSQL
  |                                  | FileIngestJob
  | 202 + job_id                     | OutboxEvent
  v                                  v
Browser polling                 Outbox dispatcher
                                     |
                                     v
                                ARQ / Redis
                                     |
                                     v
                              Backend worker
                                 |       |
                   stream object |       | update state/provenance
                                 v       v
                              MinIO/S3  PostgreSQL
                                 |
                                 | multipart + X-API-Key
                                 v
                              rag-service
                              |          |
                  pdf-inspector          | PDF scan/mixed/low confidence,
                    in process           | or every PPTX
                                         v
                                  docling-service
                                         |
                                         v
                              chunk/embed/vector store
```

Ownership boundaries:

- **Backend API:** authorization, request validation, durable job creation, status API, and user-facing file state.
- **PostgreSQL:** authoritative job state, attempt history fields, provenance, and outbox delivery intent.
- **ARQ/Redis:** at-least-once work delivery; never the only copy of job state.
- **Backend worker:** claim/lease, object download, internal REST call, response validation, retry classification, and terminal state transition.
- **Rag-service:** source-type validation, parsing, PDF routing, OCR/PPTX conversion, chunking, embedding, vector storage, and structured ingestion result.
- **Docling-service:** CPU document conversion and OCR, reachable only by rag-service.
- **Pdf-inspector:** in-process PDF classification in rag-service.

## 7. Data model

### 7.1 `file_ingest_jobs`

Add a `FileIngestJob` model and Alembic migration with these fields:

| Field | Type | Purpose |
|---|---|---|
| `id` | UUID/string PK | Public job identifier |
| `org_id` | FK, indexed | Tenant boundary |
| `file_id` | FK to uploaded file, indexed | Source upload |
| `created_by_user_id` | nullable FK | Audit actor |
| `status` | enum/string, indexed | State machine value |
| `idempotency_key` | string, indexed | Hash of immutable input and effective ingest config |
| `collection` | string | Requested RAG collection |
| `chunk_size` | integer | Effective chunk size |
| `chunk_overlap` | integer | Effective overlap |
| `tags` | JSON | Normalized tags passed to rag-service |
| `attempt_count` | integer | Number of claims that started execution |
| `max_attempts` | integer | Snapshot of policy at creation |
| `available_at` | timestamp, indexed | Earliest eligible retry time |
| `lease_owner` | nullable string | Worker claim identity |
| `lease_expires_at` | nullable timestamp, indexed | Orphan recovery boundary |
| `rag_document_id` | nullable string | Validated rag-service document ID |
| `chunk_count` | nullable integer | Validated stored chunk count |
| `source_type` | nullable string | Effective source type |
| `parser_name` | nullable string | Parser/converter used |
| `parser_version` | nullable string | Parser or service version when available |
| `pdf_classification` | nullable string | TextBased, Scanned, ImageBased, Mixed, or Unknown |
| `classification_confidence` | nullable float | Pdf-inspector confidence |
| `ocr_engine` | nullable string | OCR engine used, if any |
| `warnings` | JSON | Sanitized extraction/fallback warnings |
| `error_code` | nullable string | Stable machine-readable failure code |
| `error_detail` | nullable text | Sanitized operator-facing detail |
| `correlation_id` | string, indexed | Cross-service tracing key |
| `queued_at` | timestamp | Initial queue time |
| `started_at` | nullable timestamp | First processing start |
| `completed_at` | nullable timestamp | Terminal transition time |
| `created_at` | timestamp | Audit timestamp |
| `updated_at` | timestamp | Audit timestamp |

The effective idempotency key is SHA-256 over:

```text
org_id | file_sha256 | collection | chunk_size | chunk_overlap | canonical_tags | ingestion_contract_version
```

The file hash is calculated during upload when available; legacy uploads without a hash are hashed as a stream before the first rag-service call and then updated on the uploaded-file record.

Database invariants:

- One active job per file across `QUEUED`, `PROCESSING`, and `RETRYING`, enforced by a PostgreSQL partial unique index on `file_id`.
- A unique completed success for `(file_id, idempotency_key)` unless an explicit forced re-ingestion contract is added later.
- Tenant-safe indexes begin with `org_id` for list and lookup paths.
- Job rows are retained as audit history when an uploaded file is retained.

Phase 1 does not expose a force option. Calling ingest again with the same effective input returns the active or successful existing job. Calling it after a terminal failure creates a new job only through the retry endpoint, preserving an explicit audit trail.

### 7.2 Uploaded file state

Extend the existing file status vocabulary to:

- `uploaded`: stored and not submitted.
- `queued`: durable job exists and awaits a worker.
- `processing`: a worker owns the active lease.
- `retrying`: a transient failure is waiting for its next attempt.
- `ingested`: a validated RAG document and positive chunk count exist.
- `error`: permanent failure or exhausted retries.

Only one active job per file makes this materialized status unambiguous. Job and file state are updated in the same database transaction. Existing `uploaded`, `ingested`, and `error` rows remain valid and are not migrated into synthetic history.

## 8. State machine

```text
                      transient failure
QUEUED -> PROCESSING --------------------> RETRYING
             |                                |
             | success                        | retry due
             v                                v
         SUCCEEDED                        QUEUED
             |
             | no outgoing transition

PROCESSING -- permanent failure --------> FAILED
PROCESSING -- attempts exhausted -------> DEAD_LETTER
PROCESSING -- expired lease ------------> RETRYING
```

Terminal states are `SUCCEEDED`, `FAILED`, and `DEAD_LETTER`. Every transition is performed with a conditional update or row lock so duplicate ARQ delivery cannot execute a terminal job twice.

The database uses the uppercase state constants shown above. Public JSON and the Files UI serialize them as lowercase values (`queued`, `processing`, `retrying`, `succeeded`, `failed`, and `dead_letter`). `UploadedFile.status` retains its separate product-facing vocabulary from section 7.2.

Worker claim rules:

1. Lock the job row.
2. Ignore terminal jobs and jobs whose `available_at` is in the future.
3. If another unexpired lease exists, acknowledge the duplicate delivery without work.
4. Set `PROCESSING`, increment `attempt_count`, assign `lease_owner`, and set `lease_expires_at`.
5. Commit the claim before network I/O.

The lease duration is configurable and must exceed the configured rag-service read timeout plus object-transfer margin. Default values are a 180-second RAG read timeout and a 300-second lease. A periodic recovery task moves expired `PROCESSING` jobs to `RETRYING` with error code `WORKER_LEASE_EXPIRED`.

## 9. Durable dispatch and retry scheduling

Job creation and an existing backend `OutboxEvent` with type `file.ingest.requested` are committed in one transaction. The outbox dispatcher publishes only `{job_id, correlation_id}` to ARQ. File bytes, credentials, and user-provided metadata are not placed in Redis.

The consumer marks the current outbox event processed after it records the outcome of that attempt. For transient failures it sets `RETRYING` and `available_at`; a periodic scheduler finds due retry jobs and atomically creates a new outbox event while moving the job to `QUEUED`. This prevents a long-lived ARQ retry from becoming the authoritative schedule.

Backoff uses bounded exponential delay with jitter:

```text
delay = min(base_seconds * 2^(attempt_count - 1), max_seconds) + jitter
```

Defaults are 5 attempts, 5-second base delay, and 5-minute maximum delay. All are configurable. Exhaustion transitions to `DEAD_LETTER`; it does not silently remain in `retrying`.

Transient failures include:

- object-store timeout or temporary 5xx response;
- connection, read-timeout, or 5xx response from rag-service;
- rag-service response explicitly classified as temporary dependency failure;
- worker lease expiration.

Permanent failures include:

- unsupported extension or rejected MIME signature;
- size or decompression-safety limit violation;
- malformed ingest configuration;
- authenticated 4xx response other than an explicitly retryable rate limit;
- a completed parse with confirmed empty content and no fallback warning indicating a temporary dependency outage;
- structured success missing a document ID or having `chunk_count <= 0` (`INVALID_RAG_RESULT`).

HTTP 429 honors a bounded `Retry-After` value. Authentication failures use `RAG_AUTH_FAILED`, are permanent for the job, and trigger an operational alert because retrying cannot repair configuration.

## 10. API contract

### 10.1 Submit ingestion

`POST /api/files/{file_id}/ingest`

The existing authorization requirement remains: the caller must be allowed to manage the file in its organization. The request keeps the supported collection/chunk/tag options.

- `202 Accepted` for a newly created or already-active job.
- `200 OK` when the same input was already successfully ingested.
- `404 Not Found` for a missing or inaccessible file, preserving tenant isolation.
- `409 Conflict` only when the file has a different active ingestion configuration.
- `422 Unprocessable Entity` for invalid ingestion options.

Response:

```json
{
  "job_id": "uuid",
  "file_id": "uuid",
  "status": "queued",
  "deduplicated": false,
  "attempt_count": 0,
  "max_attempts": 5,
  "rag_document_id": null,
  "chunk_count": null,
  "warnings": [],
  "error_code": null,
  "created_at": "2026-08-17T00:00:00Z",
  "updated_at": "2026-08-17T00:00:00Z"
}
```

The API no longer waits for parsing and no longer returns a human-readable MCP result.

### 10.2 Read status and history

- `GET /api/files/{file_id}/ingest-jobs` returns newest-first history for that file.
- `GET /api/files/{file_id}/ingest-jobs/{job_id}` returns one job.

Both routes scope the query by `org_id` and file access before returning data. Cross-organization and non-owner lookups follow the existing 404 resource-hiding policy.

### 10.3 Retry terminal failure

`POST /api/files/{file_id}/ingest-jobs/{job_id}/retry`

This route requires file-management permission, accepts only `FAILED` or `DEAD_LETTER`, creates a new job linked to the same immutable input/configuration, and returns `202`. It never mutates a terminal history row back into an active state.

## 11. Backend-to-RAG contract

Add a dedicated asynchronous `RagIngestClient` in the backend. It calls:

```text
POST {RAG_SERVICE_URL}/api/v1/ingest/file
Content-Type: multipart/form-data
X-API-Key: <RAG_API_KEY>
X-Correlation-ID: <job correlation_id>
```

The client streams the S3/MinIO object into the multipart request. It does not materialize a base64 copy. The filename, collection, chunk settings, and normalized tags are sent using the existing rag-service fields.

Configuration:

- `RAG_SERVICE_URL`: explicit internal base URL; Compose supplies `http://rag-service:8100` to API and worker.
- `RAG_API_KEY`: shared service credential already supported by rag-service; required outside local development.
- `RAG_INGEST_CONNECT_TIMEOUT_SECONDS`: default 10.
- `RAG_INGEST_READ_TIMEOUT_SECONDS`: default 180.
- `FILE_INGEST_MAX_ATTEMPTS`: default 5.
- `FILE_INGEST_LEASE_SECONDS`: default 300.
- `FILE_INGEST_RETRY_BASE_SECONDS`: default 5.
- `FILE_INGEST_RETRY_MAX_SECONDS`: default 300.

Secrets are passed through deployment secret management, not committed `.env` files or job payloads.

The worker validates a typed JSON response. Success requires all of:

- response HTTP status is 2xx;
- response `status` equals `success`;
- `document_id` is non-empty;
- `chunk_count` is greater than zero.

Any parser warnings remain visible in job provenance. A warning does not invalidate success when positive text chunks were stored. A response containing no chunks can never mark the file `ingested`.

The rag-service response contract will be extended, backward-compatibly, with an optional `provenance` object containing parser/classifier/OCR fields. Backend code tolerates absent optional provenance during rolling deployment, but never relaxes the document-ID and chunk-count success checks.

## 12. PDF, Docling, and PPTX behavior

The enterprise queue does not duplicate extraction decisions:

- Text-based PDF: rag-service uses pdf-inspector classification and retains the pypdf/pdfminer fast path.
- Scanned, image-based, mixed, or low-confidence PDF: rag-service calls docling-service when `DOCLING_SERVICE_URL` is configured.
- Docling timeout/failure: rag-service attempts the existing PDF fallback, emits an explicit warning, and must not return successful empty content.
- PPTX: rag-service routes directly to docling-service.
- Pdf-inspector remains pinned to the approved fork commit in rag-service.
- Docling-service remains built from the pinned fork commit and uses the configured CPU-compatible OCR/runtime dependencies.

Backend workers never call Docling directly. This prevents parser routing policy from diverging across services.

## 13. Security and tenant isolation

- Public endpoints use the existing JWT authentication and centralized authorization helpers.
- Every job query and mutation includes `org_id`; knowing a UUID is insufficient to retrieve another tenant's job.
- Rag-service and Docling remain on the Compose internal network. Docling has no host-published port in production profiles.
- Rag-service rejects missing/invalid `X-API-Key` in production.
- The worker verifies extension, configured file-size limit, and stored-object metadata before transfer; rag-service remains the final source-type validator.
- Multipart filenames are normalized and never used as filesystem paths without sanitization.
- Logs exclude file bytes, bearer tokens, API keys, raw document content, and full untrusted exception bodies.
- Persisted error details are length-bounded and sanitized. User responses expose stable error codes and safe summaries.
- Download URLs or object-store credentials are not sent to rag-service; the trusted worker streams the object.
- Correlation IDs are generated server-side and propagated to logs and internal requests.

## 14. Observability and operations

Structured logs include `job_id`, `file_id`, `org_id`, `correlation_id`, `attempt_count`, state transition, duration, source type, and sanitized error code.

Metrics:

- jobs created, succeeded, failed, retried, and dead-lettered;
- queue wait, processing, and total latency histograms;
- active and expired leases;
- bytes streamed and rag-service request duration;
- results by source type, PDF classification, parser, and OCR engine;
- fallback warning count and invalid/empty RAG result count.

Operational alerts:

- dead-letter rate above threshold;
- oldest queued/retrying job age above service objective;
- expired lease count above threshold;
- RAG authentication failure;
- sustained rag-service or Docling 5xx/timeout rate;
- successful HTTP responses with invalid structured results.

The worker health endpoint remains the process-level signal. Queue-depth and oldest-job metrics are required as workload health signals.

## 15. UI behavior

After the user clicks Ingest, the Files UI immediately displays `Queued` and polls the job endpoint. It renders distinct `Processing`, `Retrying`, `Ingested`, `Failed`, and `Dead letter` states.

- `Retrying` shows attempt count and next retry time.
- Terminal errors show a safe summary and, for authorized users, a Retry action.
- `Ingested` is shown only after the backend job reaches `SUCCEEDED` with a document ID and positive chunk count.
- Extraction warnings remain inspectable without turning a valid ingestion into a failure.
- Navigation or browser refresh reconstructs status from PostgreSQL through the API; no client-only optimistic success state is retained.

Polling can stop at a terminal state. A future server-events transport may replace polling without changing the job contract.

## 16. Failure scenarios

| Scenario | Expected behavior |
|---|---|
| Duplicate submit during active job | Return the same job; no second active worker operation |
| API crashes after DB commit | Outbox dispatcher later publishes the committed event |
| Redis unavailable at submit time | API still records the job/outbox; dispatcher retries delivery |
| Worker crashes after claim | Lease expires; recovery moves job to retrying |
| Duplicate ARQ delivery | Conditional claim ignores leased or terminal job |
| MinIO/S3 temporary outage | Retry with backoff, then dead-letter on exhaustion |
| Rag-service timeout/5xx | Retry with backoff, preserving attempt diagnostics |
| Invalid RAG API key | Permanent failure plus operator alert |
| Unsupported or unsafe file | Permanent failure; no retry storm |
| Docling unavailable for scanned PDF | Rag-service fallback plus explicit warning; success only with positive chunks |
| Docling unavailable for PPTX | Retry dependency failure; never report empty success |
| RAG returns 2xx but zero chunks | Permanent `INVALID_RAG_RESULT`; file remains error |
| Worker completes after lease was recovered | Terminal update uses lease owner/version guard; stale worker cannot overwrite newer state |

## 17. Testing strategy

### 17.1 Unit tests

- State transition table, including rejection of invalid transitions.
- Idempotent duplicate submission and one-active-job invariant.
- Tenant/ownership checks for submit, status, history, and retry.
- Claim behavior for duplicate delivery, future retry, active lease, and terminal job.
- Error classification, bounded exponential backoff, attempt exhaustion, and dead-letter transition.
- Lease-expiration recovery and stale-worker completion guard.
- Typed RAG response validation, including false-success and malformed JSON cases.
- Provenance/warning persistence and error sanitization.

### 17.2 Integration tests

- API transaction creates both job and outbox event.
- Outbox-to-ARQ delivery contains only identifiers.
- Worker streams a stored object to a fake authenticated RAG HTTP endpoint.
- Temporary 5xx schedules a durable retry; permanent 4xx does not.
- Worker restart recovers an expired lease.
- Cross-organization job IDs return 404.
- Existing MCP configuration is neither required nor read by Files ingestion.

### 17.3 Real Compose E2E tests

At least one non-mocked test run must build and start backend API, worker, PostgreSQL, Redis, MinIO/S3, rag-service, docling-service, and the vector dependencies. It must upload through the public Files API/UI and wait on the durable job endpoint for:

1. A text-layer PDF whose expected text is present.
2. An image-only scanned PDF whose OCR marker is present when Docling is enabled.
3. A PPTX whose slide marker is present.

Each fixture is stored in the test tree or deterministically generated by test code. Assertions require a terminal `SUCCEEDED`, non-empty document ID, positive chunk count, and expected extracted marker. The scan test also asserts OCR provenance. Tests must fail if the service container cannot import its inference runtime or execute a real conversion.

Failure-injection E2E coverage stops rag-service during an attempt, verifies `RETRYING`, restarts it, and verifies eventual success. A separate bounded-attempt test verifies `DEAD_LETTER` and confirms the Files UI never displays `Ingested`.

## 18. Migration and rollout

Deployment order:

1. Apply the additive database migration.
2. Deploy rag-service response provenance support and verify its authenticated REST health.
3. Deploy backend API and worker with `RAG_SERVICE_URL` and `RAG_API_KEY` configured.
4. Deploy the Files UI status changes.
5. Run real text-PDF, scanned-PDF, and PPTX smoke jobs in a test organization.
6. Monitor queue age, retries, dead letters, OCR warnings, and RAG latency before broad rollout.

The migration is additive. Existing uploaded files keep their current status. Existing organization MCP integrations are untouched and continue serving explicit MCP use cases, but Files ingestion no longer looks up the `rag` integration.

During rolling deployment, old API instances may still use synchronous MCP ingestion. The release should therefore deploy API and worker in a coordinated maintenance window or use a short-lived feature flag to switch all API replicas after the worker and schema are ready. The feature flag is removed after successful rollout rather than retained as a permanent dual path.

Rollback stops new async submission, drains or pauses queued jobs, and restores the previous API version. The additive job table can remain. Successfully ingested vector documents are not deleted by rollback.

## 19. Acceptance criteria

The implementation is complete only when:

1. File ingest submission returns in bounded API time without waiting for parsing/OCR.
2. No organization MCP server is required for file ingestion.
3. PostgreSQL records every job and terminal outcome; Redis loss does not erase intent.
4. Duplicate submission cannot create two active jobs for one file.
5. Temporary failures visibly retry and exhausted attempts visibly dead-letter.
6. A file reaches `ingested` only with a validated document ID and positive chunk count.
7. Text PDF, scanned PDF, and PPTX pass real-container E2E tests through the product flow.
8. Scanned-PDF fallback warnings are retained and empty OCR results cannot become false success.
9. Cross-organization and unauthorized job access follows the existing 404/403 policy.
10. Docling is called only by rag-service and is not publicly exposed.
11. Service credentials and file content do not appear in Redis payloads or logs.
12. Queue latency, processing latency, retries, expired leases, and dead letters are observable.

## 20. Future evolution

If document conversion volume later requires independent scaling, rag-service may introduce its own durable queue and return a remote processing ID. The backend `FileIngestJob` remains the product-facing orchestration record and can map to that remote ID. Because this design isolates calls behind `RagIngestClient`, that evolution does not require changing authorization, UI state, or the public Files API contract.
