# Personal Email Intelligence Automation — Production Design Specification

> Ngày: 2026-08-13
> Trạng thái: Thiết kế hoàn chỉnh, chờ user review cuối cùng
> Target: Docker Compose trên một VPS, dưới 100 user
> Phạm vi tài khoản: Google Workspace và Gmail cá nhân
> Nền tảng hiện có: FastAPI, PostgreSQL 17, Redis 7, ARQ, Next.js, MinIO, SearXNG, Crawl4AI, OpenTelemetry/Prometheus/Grafana

## 1. Mục tiêu sản phẩm

Xây dựng một trợ lý email cá nhân cho từng user trong organization. Hệ thống nhận Gmail gần real-time, tải và chuẩn hóa nội dung, kiểm tra an toàn, phân loại, định tuyến và tự động tạo đầu ra phù hợp:

- email rác hoặc ít giá trị được bỏ qua hoặc gắn nhãn theo policy;
- email thông thường được tóm tắt và thông báo cho user;
- email có ý định lịch tạo Calendar proposal;
- email từ khách hàng/đối tác tạo Customer Research Case, nghiên cứu công ty và sinh briefing có nguồn;
- email nguy hiểm được hạn chế hoặc quarantine;
- mọi side effect ra Google Calendar, Gmail hoặc Knowledge Base đều đi qua approval hoặc trusted rule đã được user cấu hình rõ ràng.

Manual research tiếp tục được hỗ trợ nhưng chỉ là entry point phụ. Luồng chính của feature là Gmail event ingestion và automatic routing.

## 2. Quyết định sản phẩm đã khóa

1. Mỗi user tự kết nối Gmail, Calendar và Drive của mình; dữ liệu thuộc cả `org_id` và `user_id`.
2. Admin quản lý OAuth application, policy, quota, audit và shared connection; admin không mặc nhiên được đọc mailbox cá nhân.
3. Hỗ trợ cả Google Workspace và Gmail cá nhân.
4. Cho phép gửi phần nội dung email cần thiết tới LLM cloud theo policy dữ liệu.
5. Calendar mặc định phải chờ approval. User có thể bật auto-create theo sender/domain rule đáng tin cậy.
6. Trusted rule chỉ được auto-execute khi Guard outcome là `pass`; `restricted` luôn yêu cầu explicit approval.
7. Research tự động chỉ đến `REPORT_READY`. Gửi email, ghi Calendar và lưu Knowledge Base là lifecycle độc lập.
8. SLA mục tiêu:
   - phân loại và notification: p95 dưới 60 giây từ lúc webhook được nhận;
   - customer briefing: p95 dưới 3 phút trong điều kiện provider hoạt động bình thường.
9. PostgreSQL là nguồn sự thật. Redis/ARQ chỉ là execution transport có thể rebuild.
10. Hệ thống cung cấp effectively-once side effect. Không tuyên bố exactly-once đối với provider không có primitive idempotency.

## 3. Ngoài phạm vi phiên bản đầu

- Tự động gửi email không qua explicit approval hoặc trusted rule hợp lệ.
- Domain-wide delegation đọc toàn bộ mailbox organization.
- Xóa email vĩnh viễn; hành động xóa chỉ được hiểu là chuyển vào Trash khi được bổ sung sau này.
- Scrape sau login, vượt CAPTCHA hoặc truy cập nguồn vi phạm điều khoản sử dụng.
- Tự suy đoán dữ liệu nhạy cảm cá nhân không có nguồn.
- Thay thế CRM/ERP.
- Kafka, RabbitMQ, Temporal hoặc Kubernetes cho target dưới 100 user.
- Exactly-once tuyệt đối trên Gmail Send hoặc provider không hỗ trợ idempotency/read-back.

## 4. Kiến trúc tổng thể

```text
Gmail
  → Google Pub/Sub authenticated push (historyId)
  → Caddy HTTPS
  → FastAPI webhook: verify, persist, return 2xx
  → PostgreSQL inbox/outbox transaction
  → Redis + ARQ ingest worker
  → Gmail History Sync + checkpoint
  → Normalize MIME + deduplicate
  → Guard: URL, DLP/secret, injection, attachment/ClamAV
  → LLM Classifier/Extractor trả strict JSON
  → Deterministic Policy Router
       ├─ ignore/quarantine
       ├─ summary + notification
       ├─ calendar proposal
       └─ customer research → briefing
  → Action Proposal
  → Approval hoặc trusted rule
  → Idempotent Executor
  → Calendar / Gmail / Knowledge Base
```

Polling reconciliation chạy mỗi 5 phút để bù push bị mất. Gmail watch được kiểm tra định kỳ và renew trước khi hết hạn.

### 4.1 Lựa chọn nền tảng

| Nhu cầu | Công cụ | Lý do |
|---|---|---|
| API/webhook | FastAPI | Có sẵn, async-native, phù hợp webhook và OAuth callback |
| Business state | PostgreSQL 17 | Transaction, row lock, unique constraint, outbox, lease, audit |
| Queue | Redis 7 + ARQ | Phù hợp codebase asyncio hiện tại và quy mô dưới 100 user |
| Scheduler | ARQ cron + PostgreSQL lease | Giữ timer đơn giản nhưng occurrence và lock bền vững |
| Blob | MinIO | Attachment và artifact lớn; bytes-only |
| Malware | ClamAV daemon | Scan attachment trước khi cho phép đọc |
| Search | SearXNG | Self-hosted metasearch, giảm phụ thuộc một provider |
| Crawl | Crawl4AI | Fetch trang JS-rendered trong container riêng |
| Reverse proxy/TLS | Caddy | HTTPS tự động và cấu hình Compose gọn |
| Telemetry | OpenTelemetry + Prometheus + Grafana + Loki | Trace, metric, dashboard và alert |
| LLM tracing | Langfuse hiện có | Theo dõi latency/token/cost với content capture được kiểm soát |

RabbitMQ/Celery và Temporal không được chọn vì tăng đáng kể chi phí vận hành và buộc thay đổi worker model hiện tại mà chưa tạo giá trị tương xứng ở quy mô này.

### 4.2 Ranh giới lưu trữ

PostgreSQL giữ canonical state:

- ownership, state machine và row version;
- Gmail checkpoint, notification inbox và outbox;
- email/report metadata và encrypted content reference;
- blob key, MIME, size, SHA-256, scan status và retention deadline;
- classification, routing decision, approval, execution, attempt và audit.

MinIO chỉ giữ bytes:

- attachment được phép lưu;
- parsed artifact lớn;
- rendered PDF/DOCX;
- không lưu workflow state hoặc quyền truy cập canonical.

Mọi truy cập MinIO phải qua API đã authorize. Lifecycle deletion đọc retention policy từ PostgreSQL. Nếu xóa object thất bại, metadata giữ trạng thái `deletion_pending` để scheduler retry.

## 5. Trust boundaries và nguyên tắc an toàn

1. Pub/Sub envelope là input không tin cậy cho đến khi JWT, issuer, audience và service-account identity được verify.
2. Gmail body, header, URL và attachment là untrusted data, không phải instruction.
3. Webhook không tải email và không gọi LLM.
4. Guard chạy trước mọi LLM call.
5. LLM chỉ trả data theo versioned JSON Schema; không được gọi action trực tiếp.
6. Policy Router là code deterministic, không phải prompt.
7. Queue payload không chứa email body, OAuth token, recipient body hoặc attachment bytes.
8. Worker không tin `org_id/user_id` trong queue; luôn reload và verify ownership từ database.
9. Side effect phải có proposal version, server-computed payload hash, approval scope, expiry và idempotency key.
10. Ambiguous provider write chuyển `RECONCILING` hoặc `MANUAL_REVIEW`; không retry write mù.

## 6. Data flow chi tiết

### 6.1 Gmail push hot path

1. Pub/Sub gọi `POST /api/webhooks/google/gmail` qua HTTPS.
2. API verify OIDC JWT signature, issuer, `aud`, service-account email và token age.
3. API validate envelope size và base64 payload.
4. API tìm connection theo Gmail account; không nhận `org_id/user_id` từ request.
5. API insert notification với unique `(connection_id, history_id)`.
6. Cùng transaction, API update `highest_pending_history_id` và ghi outbox event.
7. Duplicate notification vẫn trả `204`.
8. API trả `204` sau commit; không chờ Redis hoặc Gmail API.

`notification_id` chỉ phục vụ trace. Push, reconciliation và manual sync trỏ cùng `history_id` đều dedupe theo `(connection_id, history_id)`.

### 6.2 History sync

1. Worker claim lease theo connection.
2. Đọc `checkpoint_history_id` và `highest_pending_history_id`.
3. Gọi Gmail History API từ checkpoint hiện tại đến target cao nhất.
4. Fetch message theo provider message ID.
5. Dedupe bằng unique `(connection_id, provider_message_id)`.
6. Normalize email và attachment metadata.
7. Ghi email, attachment metadata và outbox event trong transaction.
8. Chỉ advance checkpoint sau khi toàn bộ batch được ghi bền vững.
9. Nếu target tăng trong lúc chạy, enqueue lượt tiếp theo.
10. Release lease.

Nếu history ID quá cũ, worker chạy bounded reconciliation theo lookback window cấu hình, mặc định 7 ngày và tối đa 30 ngày; không quét mailbox vô hạn.

### 6.3 Normalize & Guard

Normalize thực hiện:

- parse MIME với giới hạn recursion và tổng kích thước;
- chuẩn hóa sender, recipient, subject, plain text và HTML;
- không tải remote image;
- tách URL nhưng chưa fetch;
- ghi attachment metadata và bytes vào quarantine bucket nếu policy cho phép;
- tính content SHA-256 và attachment SHA-256.

Guard thực hiện:

- loại file/kích thước và MIME mismatch;
- ClamAV scan attachment;
- URL normalization và safety check;
- block private, loopback, link-local, metadata endpoint và unsafe redirect;
- deterministic prompt-injection heuristics;
- DLP/secret detection và redaction profile;
- tạo immutable Guard Decision gắn đúng `content_revision`.

### 6.4 Classification và routing

Classifier nhận nội dung đã được Guard cho phép và đặt trong delimiter tách biệt với system instruction. Output phải validate strict JSON Schema với `extra=forbid`.

Policy Router đọc classification, Guard Decision, tenant policy, user rule và confidence threshold. Router transactionally:

1. ghi routing decision;
2. tạo child aggregate cần thiết;
3. ghi outbox event;
4. chuyển email sang `ROUTING_COMPLETED`;
5. commit một lần.

### 6.5 Research và action

Customer Research chạy các branch web/news, company database, calendar và approved memory. Branch độc lập có timeout và retry riêng. Partial failure vẫn có thể tạo report nếu report ghi rõ missing data, warning và confidence.

Research chỉ kết thúc ở `REPORT_READY`. Calendar create, Gmail draft/send và Knowledge Base save bắt đầu từ Action Proposal độc lập.

## 7. State machines

### 7.1 Email processing

```text
DISCOVERED → FETCHED → NORMALIZED → GUARDED → CLASSIFIED
→ ROUTED → ROUTING_COMPLETED
```

Failure của stage hiện tại:

```text
<CURRENT_STAGE> → RETRY_SCHEDULED → <CURRENT_STAGE>
RETRY_SCHEDULED → DEAD_LETTER khi hết giới hạn
```

Terminal alternatives:

```text
IGNORED | QUARANTINED | REJECTED | DEAD_LETTER | ROUTING_COMPLETED
```

`ROUTING_COMPLETED` chỉ có nghĩa routing decision và child row/outbox đã commit. Nó không có nghĩa downstream research/action đã thành công.

### 7.2 Guard

```text
PENDING → SCANNING → PASS | RESTRICTED | QUARANTINE | REJECT
```

| Outcome | Classifier | URL/attachment | Action policy |
|---|---|---|---|
| `pass` | Full allowed content | Theo policy thường | Trusted rule có thể được xét |
| `restricted` | Sanitized text | Không dùng attachment/email URL | Explicit approval bắt buộc |
| `quarantine` | Không gửi body tới LLM | Không truy cập | Metadata-only notification, không proposal |
| `reject` | Không chạy | Không truy cập | Dừng pipeline, audit reason |

Với `restricted`, customer research chỉ được dùng sender/domain đã xác minh và nguồn search an toàn.

### 7.3 Research Case

```text
NEW → QUEUED → RESEARCHING → REPORT_READY
RESEARCHING → RETRY_SCHEDULED → QUEUED
RETRY_SCHEDULED → DEAD_LETTER
NEW|QUEUED|RESEARCHING → CANCEL_REQUESTED → CANCELLED
```

Cancel và worker finalize dùng conditional update với `row_version`. Commit thắng trước quyết định kết quả. Sau `REPORT_READY`, report là artifact bất biến và case không còn cancel được.

### 7.4 Action Proposal và execution

```text
PROPOSED → AWAITING_APPROVAL → APPROVED → EXECUTING → SUCCEEDED
PROPOSED → APPROVED                         # trusted rule hợp lệ
AWAITING_APPROVAL → REJECTED | EXPIRED
PROPOSED|AWAITING_APPROVAL|APPROVED → CANCELLED
APPROVED → INVALIDATED
EXECUTING → RETRY_SCHEDULED → EXECUTING
EXECUTING → RECONCILING → SUCCEEDED | MANUAL_REVIEW
EXECUTING → FAILED
```

Proposal cancellation và executor claim cạnh tranh bằng atomic compare-and-set trên cùng row/version. Sau khi executor đã claim `EXECUTING`, cancel trả HTTP `409`.

Precondition failure chuyển Proposal thành `INVALIDATED` và ActionExecution thành `REJECTED_PRECONDITION`; không map chung vào provider `FAILED`.

### 7.5 User-facing aggregate projection

UI không suy status từ email state đơn lẻ. Read model join email, case, proposal và execution:

| Canonical states | UI status |
|---|---|
| Email `ROUTING_COMPLETED`, Case `QUEUED/RESEARCHING` | Researching |
| Case `REPORT_READY` | Briefing ready |
| Proposal `AWAITING_APPROVAL` | Needs approval |
| Downstream `DEAD_LETTER/FAILED/MANUAL_REVIEW` | Needs attention |
| Mọi child route đã terminal-success/no-action | Completed |

Projection là read-only và rebuildable, không phải workflow truth.

## 8. Versioned contracts

### 8.1 Common Event Envelope

```json
{
  "schema_version": "1.0",
  "event_type": "email.guard_completed",
  "event_id": "uuid",
  "occurred_at": "2026-08-13T04:00:00Z",
  "correlation_id": "uuid",
  "causation_id": "uuid",
  "org_id": "uuid",
  "user_id": "uuid",
  "aggregate_type": "inbound_email",
  "aggregate_id": "uuid",
  "aggregate_version": 4,
  "payload": {}
}
```

`event_id` là consumer idempotency key. Timestamp dùng UTC RFC 3339. Unknown enum hoặc field thiếu làm validation fail closed.

### 8.2 History Sync Requested

```json
{
  "schema_version": "1.0",
  "connection_id": "uuid",
  "notification_id": "trace-only-id",
  "history_id": "987654321",
  "source": "pubsub",
  "received_at": "2026-08-13T04:00:00Z"
}
```

`source` là `pubsub`, `reconciliation` hoặc `manual`. Idempotency dùng `(connection_id, history_id)`.

### 8.3 Normalize Result

```json
{
  "schema_version": "1.0",
  "email_id": "uuid",
  "connection_id": "uuid",
  "content_revision": 1,
  "provider_message_id": "gmail-message-id",
  "content_sha256": "hex-sha256",
  "attachment_ids": ["uuid"],
  "normalization": {
    "mime_valid": true,
    "body_format": "plain_text",
    "truncated": false,
    "warnings": []
  }
}
```

Contract không chứa body; worker đọc canonical content qua `email_id`.

### 8.4 Guard Decision

```json
{
  "schema_version": "1.0",
  "guard_decision_id": "uuid",
  "email_id": "uuid",
  "content_revision": 1,
  "outcome": "restricted",
  "classifier_access": {
    "allowed": true,
    "body_mode": "sanitized",
    "allow_email_urls": false,
    "allow_attachments": false
  },
  "policy": {
    "trusted_rule_eligible": false,
    "explicit_approval_required": true,
    "redaction_profile": "cloud-llm-default-v1"
  },
  "reasons": [
    {
      "code": "PROMPT_INJECTION_SUSPECTED",
      "severity": "high",
      "evidence_sha256": "hex-sha256"
    }
  ],
  "scanners": [
    {"name": "prompt-injection-heuristics", "version": "1.0.0", "result": "flagged"},
    {"name": "clamav", "version": "1.4.3", "result": "clean"},
    {"name": "url-safety", "version": "1.0.0", "result": "restricted"},
    {"name": "dlp-secret-redactor", "version": "1.0.0", "result": "redacted", "redaction_count": 2}
  ],
  "completed_at": "2026-08-13T04:00:04Z"
}
```

Evidence chỉ lưu hash/reason code, không ghi raw secret trong log hoặc trace.

### 8.5 Classifier Output

```json
{
  "schema_version": "1.0",
  "email_id": "uuid",
  "content_revision": 1,
  "guard_decision_id": "uuid",
  "classifier": {
    "model_id": "configured-model-id",
    "prompt_version": "email-classifier-v1",
    "output_schema": "email-classification-v1"
  },
  "labels": [
    {"code": "customer", "confidence": 0.94},
    {"code": "calendar", "confidence": 0.82}
  ],
  "summary": {
    "short_text": "Khách hàng đề nghị họp để trao đổi giải pháp.",
    "action_items": [{"text": "Xác nhận thời gian họp", "confidence": 0.87}]
  },
  "calendar_candidates": [
    {
      "title": "Trao đổi giải pháp",
      "start_at": "2026-08-15T02:00:00Z",
      "end_at": "2026-08-15T03:00:00Z",
      "timezone": "Asia/Ho_Chi_Minh",
      "attendees": ["customer@example.com"],
      "location": null,
      "confidence": 0.82,
      "uncertain_fields": []
    }
  ],
  "customer_candidates": [
    {
      "name": "Example Company",
      "domain": "example.com",
      "contact_email": "customer@example.com",
      "confidence": 0.94
    }
  ],
  "warnings": []
}
```

Label hợp lệ: `spam`, `normal`, `calendar`, `customer`, `partner`, `security_risk`, `newsletter`, `transactional`. Classifier không có field execute/send/create.

### 8.6 Routing Decision

```json
{
  "schema_version": "1.0",
  "routing_decision_id": "uuid",
  "email_id": "uuid",
  "email_version": 6,
  "guard_decision_id": "uuid",
  "classification_id": "uuid",
  "policy_version": "email-routing-v1",
  "routes": [
    {"type": "notify_summary", "mode": "dispatch", "reason_codes": ["NORMAL_EMAIL_SUMMARY"]},
    {"type": "customer_research", "mode": "dispatch", "reason_codes": ["CUSTOMER_CONFIDENCE_THRESHOLD_MET"]},
    {"type": "calendar_proposal", "mode": "dispatch", "reason_codes": ["CALENDAR_INTENT_DETECTED"], "approval_mode": "explicit"}
  ],
  "suppressed_routes": [
    {"type": "calendar_auto_create", "reason_code": "GUARD_RESTRICTED"}
  ],
  "decided_at": "2026-08-13T04:00:08Z"
}
```

`suppressed_routes` là bắt buộc khi một classification label có route tiềm năng nhưng bị policy chặn.

### 8.7 Research Result

```json
{
  "schema_version": "1.0",
  "case_id": "uuid",
  "case_version": 5,
  "input_snapshot_sha256": "hex-sha256",
  "research_policy_version": "customer-research-v1",
  "status": "partial",
  "company": {
    "canonical_name": "Example Company",
    "domain": "example.com",
    "confidence": 0.93
  },
  "branches": [
    {"name": "web", "status": "succeeded", "source_ids": ["uuid"], "warning_codes": []},
    {"name": "calendar", "status": "unavailable", "source_ids": [], "warning_codes": ["NO_CALENDAR_CONNECTION"]}
  ],
  "report": {
    "report_id": "uuid",
    "version": 1,
    "content_sha256": "hex-sha256",
    "section_codes": [
      "executive_summary",
      "company_overview",
      "recent_news",
      "contact_information",
      "upcoming_meetings",
      "open_questions",
      "sources"
    ],
    "confidence": 0.81
  },
  "completed_at": "2026-08-13T04:02:10Z"
}
```

`status` là `complete`, `partial` hoặc `failed`. Mỗi external claim trong report phải tham chiếu source ID.

### 8.8 Action Proposal

```json
{
  "schema_version": "1.0",
  "proposal_id": "uuid",
  "proposal_version": 1,
  "org_id": "uuid",
  "user_id": "uuid",
  "source": {"email_id": "uuid", "case_id": "uuid", "report_id": "uuid"},
  "action_type": "calendar.create",
  "target_connection_id": "uuid",
  "payload": {
    "title": "Trao đổi giải pháp",
    "start_at": "2026-08-15T02:00:00Z",
    "end_at": "2026-08-15T03:00:00Z",
    "timezone": "Asia/Ho_Chi_Minh",
    "attendees": ["customer@example.com"],
    "location": null,
    "description": "Generated from email uuid"
  },
  "payload_sha256": "hex-sha256",
  "risk_level": "medium",
  "approval_mode": "explicit",
  "trusted_rule_snapshot": null,
  "expires_at": "2026-08-14T04:02:10Z",
  "created_at": "2026-08-13T04:02:10Z"
}
```

Action type v1:

```text
calendar.create
gmail.create_draft
gmail.send_draft
gmail.apply_label
gmail.archive
knowledge.save
```

Server tính `payload_sha256` từ canonical JSON. Edit tạo proposal version mới; approval cũ mất hiệu lực.

### 8.9 Approval Decision

Client request:

```json
{
  "decision": "approved",
  "reason": "",
  "expected_proposal_version": 1
}
```

Immutable server event:

```json
{
  "schema_version": "1.0",
  "approval_id": "uuid",
  "proposal_id": "uuid",
  "proposal_version": 1,
  "payload_sha256": "hex-sha256",
  "decision": "approved",
  "decision_source": "user",
  "scope": {"action_type": "calendar.create", "target_connection_id": "uuid"},
  "decided_by_user_id": "uuid",
  "reason": "",
  "decided_at": "2026-08-13T04:05:00Z",
  "valid_until": "2026-08-14T04:02:10Z"
}
```

Server lấy actor từ JWT. Trusted rule dùng `decision_source=trusted_rule`, `trusted_rule_id`, `trusted_rule_version` và không có `decided_by_user_id`.

### 8.10 Executor Command

Queue payload:

```json
{
  "schema_version": "1.0",
  "proposal_id": "uuid",
  "proposal_version": 1,
  "execution_id": "uuid"
}
```

Worker reload canonical data và kiểm tra ownership, version, hash, approval/rule scope, expiry, connection, OAuth scope, idempotency record và atomic claim trước network call.

### 8.11 Executor Result

```json
{
  "schema_version": "1.0",
  "execution_id": "uuid",
  "proposal_id": "uuid",
  "proposal_version": 1,
  "idempotency_key": "uuid",
  "status": "succeeded",
  "provider": {
    "type": "google_calendar",
    "resource_id": "deterministic-event-id",
    "duplicate_detected": false
  },
  "attempt_count": 1,
  "side_effect_at": "2026-08-13T04:05:03Z",
  "reconciliation": {"required": false, "method": null},
  "error": null,
  "completed_at": "2026-08-13T04:05:03Z"
}
```

Execution status: `succeeded`, `retry_scheduled`, `reconciling`, `manual_review`, `failed`, `rejected_precondition`, `closed_not_applied`, `abandoned`.

### 8.12 Manual Review Resolution

```json
{
  "schema_version": "1.0",
  "resolution_id": "uuid",
  "execution_id": "uuid",
  "expected_execution_version": 4,
  "resolution": "observed_applied",
  "evidence": {
    "provider_resource_id": "provider-id",
    "observed_at": "2026-08-13T04:20:00Z",
    "evidence_sha256": "hex-sha256",
    "note": "Message found in Gmail Sent"
  },
  "resolved_by_user_id": "uuid",
  "resolved_at": "2026-08-13T04:21:00Z"
}
```

Resolution:

- `observed_applied` → `SUCCEEDED`;
- `confirmed_not_applied` → `CLOSED_NOT_APPLIED`;
- `abandon_unknown` → `ABANDONED`;
- `retry_reconciliation` → `RECONCILING`, chỉ read-only lookup.

Không resolution nào chuyển trực tiếp về `EXECUTING`. Muốn thử write lại phải tạo proposal mới và approval mới.

## 9. Idempotency và provider reconciliation

### 9.1 Logical execution

Một side effect logic có một `ActionExecution` và nhiều `DeliveryAttempt`.

Idempotency key:

```text
UUIDv5(
  namespace = organization_id,
  name = action_type + proposal_id + proposal_version + payload_sha256
)
```

Unique constraint: `(org_id, idempotency_key)`.

### 9.2 Google Calendar

Calendar event ID được derive từ idempotency key và encode base32hex hợp lệ. Client-generated event ID giúp đồng bộ local/provider và ngăn duplicate khi operation thành công ở Calendar nhưng response bị mất. Khi insert conflict, executor gọi `events.get`; payload hash khớp thì đánh dấu `SUCCEEDED`, khác thì `MANUAL_REVIEW`.

### 9.3 Gmail draft/send

1. Tạo draft trước khi send.
2. Gắn deterministic RFC `Message-ID` và `X-OpenAgent-Action-ID` vào MIME.
3. Persist `provider_draft_id` trước send.
4. Chỉ gửi đúng draft đã persist.
5. Timeout sau send chuyển `RECONCILING`.
6. Reconciler tìm message trong Sent bằng deterministic RFC Message-ID.
7. Tìm thấy thì `SUCCEEDED`.
8. Chứng minh chưa gửi thì đóng execution cũ `CLOSED_NOT_APPLIED`; muốn gửi lại phải tạo proposal mới.
9. Không chứng minh được thì `MANUAL_REVIEW`.

### 9.4 Knowledge Base

Internal KB dùng database unique idempotency key. External KB phải có idempotency key hoặc read-after-write lookup. Provider không có cả hai thì ambiguous timeout chuyển `MANUAL_REVIEW`.

## 10. Queue và scheduler foundation

### 10.1 Service topology

```text
api
scheduler-dispatcher
worker-ingest
worker-classify
worker-research
worker-actions
postgres
redis
minio
clamav
searxng
crawler
caddy
prometheus/grafana/loki/otel-collector
```

Các worker dùng chung backend image, khác command và queue.

| Worker | Concurrency mặc định | Job timeout |
|---|---:|---:|
| ingest | 4 | 120 giây |
| classify | 4 | 90 giây |
| research | 2 | 180 giây |
| actions | 2 | 90 giây |

Tất cả concurrency/timeout cấu hình bằng environment variable.

### 10.2 Queue topology

```text
ci:ingest
ci:classify
ci:research
ci:actions
ci:maintenance
```

Slow research không chia queue với realtime ingest/classification. Batch research ngừng dispatch trước khi ảnh hưởng realtime workload.

### 10.3 Transactional outbox

Dispatcher poll mỗi giây, claim tối đa 100 row bằng `FOR UPDATE SKIP LOCKED`, lease 30 giây, enqueue với `job_id=event_id`, rồi đánh dấu published. Crash sau enqueue nhưng trước update có thể tạo duplicate delivery; consumer dedupe bằng unique `(event_id, consumer_name)`.

Transport guarantee là at-least-once với idempotent consumer.

### 10.4 Gmail connection lease

Mỗi connection chỉ có một sync lease. Worker gộp target thành `highest_pending_history_id`, đọc checkpoint dưới lock, ingest idempotently và CAS checkpoint. Correctness không phụ thuộc in-memory lock.

### 10.5 Scheduled jobs

| Job | Chu kỳ | Chức năng |
|---|---:|---|
| Outbox dispatch | 1 giây | Publish durable event |
| Gmail reconciliation | 5 phút | Bù push bị mất |
| Gmail watch renewal | 12 giờ | Renew khi expiry dưới 48 giờ |
| Due retry dispatch | 15 giây | Enqueue retry đến hạn |
| Stale lease recovery | 1 phút | Thu hồi lease worker chết |
| Action reconciliation | 1 phút | Resolve ambiguous provider result |
| Manual-review reminder | 6 giờ | Nhắc owner |
| Daily digest | Theo timezone user | Tổng hợp email/report |
| Retention cleanup | Hằng ngày | Xóa dữ liệu hết hạn |
| Backup verification | Hằng ngày | Kiểm tra backup artifact đọc được |

Mọi cron có occurrence key unique `(job_key, scheduled_for_utc)` và PostgreSQL lease. User timezone chỉ dùng tính occurrence; database lưu UTC. IANA timezone là bắt buộc.

### 10.6 Retry matrix

| Error | Policy |
|---|---|
| Network failure trước request | Exponential backoff + full jitter |
| HTTP 429 | Tôn trọng `Retry-After`, giảm concurrency |
| HTTP 5xx | Retry giới hạn |
| OAuth 401 | Refresh token một lần |
| OAuth `invalid_grant` | `reauth_required`, không retry |
| LLM schema invalid | Tối đa 2 repair retry, sau đó manual review/dead-letter |
| Provider timeout sau write | `RECONCILING`, không write lại |
| Precondition/policy failure | `INVALIDATED`, không retry |
| Permanent 4xx | terminal failure |

Backoff mặc định base 2 giây, full jitter, cap 15 phút. Ingest/read tối đa 10 attempts; classifier 3; mỗi research branch 4. Action write chỉ retry khi chắc chắn provider chưa nhận request.

### 10.7 Backpressure và rate limit

- Redis token bucket theo provider, user, connection và action type.
- PostgreSQL `next_allowed_at` giữ throttling quan trọng qua Redis restart.
- Một Gmail sync đồng thời mỗi connection.
- Tối đa hai Gmail API request đồng thời mỗi connection.
- Tối đa hai research case chạy đồng thời và 20 pending mỗi user.
- Tối đa một action write đồng thời mỗi target connection.
- API user workload trả `429` với `Retry-After` khi vượt quota.
- Pub/Sub webhook vẫn persist notification khi backlog cao; không trả `429` chỉ vì worker bận.

### 10.8 Dead-letter và recovery

Dead-letter nằm trong PostgreSQL, không phụ thuộc Redis DLQ. Manual retry tạo recovery event mới với `causation_id` trỏ failure cũ, kiểm tra state hiện tại và audit actor/reason. Side effect ở `MANUAL_REVIEW` không có nút retry write.

## 11. Data model và migration requirements

Migration phải additive trước, backfill theo batch, chuyển read/write path, rồi mới remove field cũ ở release sau. Không đổi migration đã được merge.

### 11.1 `ci_connections` mở rộng

| Column | Type | Constraint/meaning |
|---|---|---|
| `created_by_user_id` | FK users | Owner cá nhân; shared connection phải có flag/scope riêng |
| `granted_scopes` | JSON | Scope thực tế Google trả về |
| `credential_key_id` | String | Key version dùng encrypt credential |
| `watch_expiration_at` | DateTime | Gmail watch expiry |
| `checkpoint_history_id` | String | Cursor đã ingest bền vững |
| `highest_pending_history_id` | String | Target lớn nhất đã nhận |
| `sync_lease_owner` | String nullable | Worker giữ lease |
| `sync_lease_until` | DateTime nullable | Lease expiry |
| `next_allowed_at` | DateTime nullable | Provider throttle bền vững |
| `row_version` | Integer | Optimistic concurrency |
| `status` | String | `connected`, `reauth_required`, `disconnected`, `error` |

Unique `(org_id, provider, account_email)` ngăn cùng một Google account được nối hai lần trong một organization. Shared connection phải được biểu diễn bằng `connection_scope=shared` và policy riêng, không dùng `created_by_user_id=NULL` như một shortcut mơ hồ.

### 11.2 `gmail_notifications`

| Column | Type | Constraint/meaning |
|---|---|---|
| `id` | UUID | PK |
| `connection_id` | FK | NOT NULL |
| `history_id` | String | NOT NULL |
| `notification_id` | String nullable | Trace-only |
| `source` | String | `pubsub`, `reconciliation`, `manual` |
| `received_at` | DateTime | NOT NULL |
| `processed_at` | DateTime nullable | |

Unique `(connection_id, history_id)`.

### 11.3 `ci_emails` mở rộng

| Column | Type | Constraint/meaning |
|---|---|---|
| `created_by_user_id` | FK users | NOT NULL sau backfill |
| `processing_status` | String | Email state machine |
| `current_stage` | String | Resume exact stage |
| `content_revision` | Integer | Bắt đầu 1 |
| `content_sha256` | String(64) | Dedupe/integrity |
| `sensitive_content_enc` | Text | Encrypted normalized body/HTML |
| `guard_decision_id` | FK nullable | Latest matching revision |
| `classification_id` | FK nullable | Latest matching revision |
| `routing_decision_id` | FK nullable | Latest routing |
| `row_version` | Integer | CAS |
| `retry_count` | Integer | Stage retry |
| `next_retry_at` | DateTime nullable | |
| `retention_until` | DateTime | |

Unique `(org_id, connection_id, provider_message_id)`. Index `(created_by_user_id, processing_status, received_at)`.

Email body và HTML không được ghi vào structured log. Production dùng AES-256-GCM theo pattern `credential_secrets.py` hiện có cho sensitive content; nonce ngẫu nhiên riêng mỗi ciphertext, deployment key nằm ngoài database và có key ID để rotation. Subject/sender metadata được giữ queryable nhưng volume và backup vẫn phải encrypted.

### 11.4 `ci_attachments`

| Column | Type | Constraint/meaning |
|---|---|---|
| `id` | UUID | PK |
| `email_id` | FK | NOT NULL |
| `filename` | String | Sanitized display name |
| `declared_mime` | String | Gmail metadata |
| `detected_mime` | String nullable | Scanner result |
| `size_bytes` | BigInteger | Limit enforcement |
| `sha256` | String(64) | Integrity/dedupe |
| `object_key` | String nullable | MinIO key |
| `scan_status` | String | `pending`, `scanning`, `clean`, `infected`, `failed`, `deletion_pending` |
| `scan_engine_version` | String nullable | |
| `retention_until` | DateTime | |

Object key không được trả trực tiếp cho browser. Download qua authorized streaming endpoint hoặc short-lived presigned URL sau ownership và scan-status check.

### 11.5 `ci_guard_decisions`

Lưu immutable JSON contract, indexed columns `email_id`, `content_revision`, `outcome`, `completed_at`, cùng `contract_json`. Unique `(email_id, content_revision)`.

### 11.6 `ci_classifications`

Lưu immutable strict output. Key columns: `email_id`, `content_revision`, `guard_decision_id`, `schema_version`, `model_id`, `prompt_version`, `labels_json`, `result_json`, `created_at`. Unique `(email_id, content_revision, prompt_version, model_id)` cho một accepted result; failed attempt nằm trong attempt/audit table.

### 11.7 `ci_routing_decisions`

Lưu immutable decision và `policy_version`, `routes_json`, `suppressed_routes_json`, `classification_id`, `guard_decision_id`. Unique theo accepted `(email_id, email_version)`.

### 11.8 `ci_cases` mở rộng

Thêm/chuẩn hóa:

- `created_by_user_id NOT NULL` sau backfill;
- `row_version`;
- `input_snapshot_sha256`;
- `cancel_requested_at`, `cancelled_at`;
- `current_stage`, `retry_count`, `next_retry_at`;
- `status` theo Research Case state machine;
- `trigger` nhận `email`, `manual`, `scheduled`, `recovery`.

Một email có tối đa một active customer research case cho cùng `input_snapshot_sha256`; unique partial index ngăn dispatch trùng.

### 11.9 `ci_reports` mở rộng

Thêm `created_by_user_id`, `input_snapshot_sha256`, `content_sha256`, `warnings_json`, `missing_data_json`, `provenance_version` và `canonical_markdown_enc`. Canonical Markdown được AES-256-GCM encrypt trong PostgreSQL; HTML/PDF/DOCX rendering lớn nằm trong MinIO với metadata/checksum ở PostgreSQL. Unique `(org_id, case_id, version)` giữ nguyên.

### 11.10 `ci_action_proposals` và `ci_action_proposal_versions`

| Column | Type | Constraint/meaning |
|---|---|---|
| `id` | UUID | PK |
| `org_id`, `user_id` | FK | Ownership |
| `email_id`, `case_id`, `report_id` | FK nullable | Provenance |
| `current_version` | Integer | Accepted proposal revision |
| `action_type` | String | Allowlisted enum |
| `target_connection_id` | FK | NOT NULL cho Google action |
| `status` | String | Proposal state machine |
| `row_version` | Integer | CAS |
| `expires_at` | DateTime | |

`ci_action_proposal_versions` là immutable history với PK riêng, FK `proposal_id`, `version`, `payload_enc`, `payload_sha256`, `risk_level`, `approval_mode`, `trusted_rule_snapshot`, `created_by_user_id` và `created_at`. Unique `(proposal_id, version)`. Proposal edit insert version row mới, tăng `current_version`, chuyển approval cũ thành invalid và không overwrite payload cũ. Index logical proposal `(user_id, status, created_at)`.

### 11.11 `approval_requests` mở rộng

Tái sử dụng approval infrastructure hiện có, thêm:

- `proposal_id`, `proposal_version`;
- `decision_source`;
- `scope_snapshot`;
- `valid_until`;
- `trusted_rule_id`, `trusted_rule_version`;
- unique `(proposal_id, proposal_version, payload_hash)` cho active approval.

Legacy `args_snapshot` được giữ để tương thích, nhưng CI executor đọc proposal canonical thay vì tin `args_snapshot`.

### 11.12 `ci_action_executions`, `delivery_attempts`, `ci_manual_review_resolutions`

`ci_action_executions` giữ một logical action, unique `(org_id, idempotency_key)`. `delivery_attempts` bỏ unique idempotency key hiện tại, thêm `execution_id` và unique `(execution_id, attempt_number)`. Migration phải backfill mỗi DeliveryAttempt cũ thành một ActionExecution tương ứng trước khi thay constraint.

Manual review resolution là immutable append-only row; update execution cùng transaction và CAS `expected_execution_version`.

### 11.13 `ci_trusted_rules`

Rule chứa owner, enabled, version, allowed action types, exact sender hoặc verified domain, confidence threshold, target connection, max actions/day, expiry và audit fields. Wildcard public suffix bị cấm. Rule edit tăng version; snapshot cũ không tự mở rộng quyền.

### 11.14 Infrastructure tables

- `outbox_events`: durable publish state và lease.
- `processed_events`: unique `(event_id, consumer_name)`.
- `job_failures`: dead-letter/recovery metadata.
- `job_schedule_executions`: occurrence unique và lease hiện có.
- `ci_notifications`: canonical in-app notification, read status và aggregate links.

Mọi tenant-owned table có composite index bắt đầu bằng `org_id`; personal query thêm `created_by_user_id/user_id` trong predicate và index.

## 12. API surface

### 12.1 Webhook và internal operations

| Method/path | Auth | Behavior |
|---|---|---|
| `POST /api/webhooks/google/gmail` | Pub/Sub OIDC JWT | Persist/dedupe history notification, trả `204` |
| `POST /internal/jobs/outbox/dispatch` | Không public | Không expose qua Caddy; scheduler gọi nội bộ nếu cần |
| `GET /readyz` | Internal/monitoring | Check PostgreSQL, Redis và migration head |
| `GET /healthz` | Public-safe | Liveness thuần, không lộ dependency detail |

Webhook body tối đa 64 KiB; request lớn hơn trả `413`. JWT sai trả `401/403`. Payload malformed trả `400`; duplicate hợp lệ trả `204`.

### 12.2 Connections

| Method/path | Permission | Behavior |
|---|---|---|
| `GET /api/customer-intelligence/connections` | `ci:read` | Chỉ own connections; admin shared scope theo policy |
| `GET /oauth/{kind}/google/start` | authenticated user | Incremental OAuth start với signed state |
| `GET /oauth/{kind}/google/callback` | signed state | Exchange token, bind đúng user/org |
| `DELETE /connections/{id}` | owner | Revoke token, stop watch, mark disconnected |
| `POST /connections/{id}/sync` | owner | Tạo durable manual sync event, trả `202` |
| `POST /connections/{id}/reauthorize` | owner | Bắt đầu OAuth lại với scope thiếu |

OAuth callback không dựa vào current browser organization đơn thuần; signed state bind `user_id`, `org_id`, connector kind, nonce, expiry và redirect allowlist.

### 12.3 Inbox intelligence

| Method/path | Behavior |
|---|---|
| `GET /api/email-intelligence/emails` | Cursor pagination, filter status/label/date |
| `GET /api/email-intelligence/emails/{id}` | Email metadata, summary, guard warning, aggregate status |
| `POST /api/email-intelligence/emails/{id}/reprocess` | Tạo revision/recovery event khi state cho phép |
| `GET /api/email-intelligence/notifications` | Own unread/read notifications |
| `POST /api/email-intelligence/notifications/{id}/read` | Mark read idempotently |
| `GET /api/email-intelligence/stream` | SSE realtime notification; reconnect rồi fetch canonical REST |

List mặc định không trả body đầy đủ. Detail chỉ decrypt sau authorization. SSE event chỉ chứa notification ID/type; client fetch detail qua REST.

### 12.4 Research

| Method/path | Behavior |
|---|---|
| `GET /api/customer-intelligence/cases` | Own cases, cursor pagination |
| `POST /api/customer-intelligence/cases/manual` | Create manual case, trả `202` |
| `GET /api/customer-intelligence/cases/{id}` | Aggregate case/report/source status |
| `POST /api/customer-intelligence/cases/{id}/cancel` | CAS cancel, `409` nếu đã `REPORT_READY` |
| `POST /api/customer-intelligence/cases/{id}/retry` | Recovery event cho eligible dead-letter only |

Không giữ endpoint chạy research inline. Endpoint create/retry chỉ ghi DB/outbox và trả `202` với resource ID.

### 12.5 Proposals, approvals và manual review

| Method/path | Behavior |
|---|---|
| `GET /api/actions/proposals` | Own proposals, filter status/action |
| `GET /api/actions/proposals/{id}` | Decrypted review payload sau authorization |
| `PATCH /api/actions/proposals/{id}` | Edit tạo proposal version mới |
| `POST /api/actions/proposals/{id}/decision` | Approve/reject với expected version |
| `POST /api/actions/proposals/{id}/cancel` | CAS cancel trước executor claim |
| `GET /api/actions/manual-reviews` | Own unresolved ambiguous writes |
| `POST /api/actions/executions/{id}/resolve` | ManualReviewResolution với expected version |

Mọi mutation hỗ trợ `Idempotency-Key` request header. Server lưu request key theo user/endpoint trong retention window để retry HTTP không tạo duplicate proposal/decision.

### 12.6 Trusted rules và schedules

| Method/path | Behavior |
|---|---|
| `GET/POST /api/email-intelligence/trusted-rules` | List/create own rules |
| `PATCH/DELETE /api/email-intelligence/trusted-rules/{id}` | Versioned update/disable |
| `GET/POST /api/customer-intelligence/schedules` | Own schedule |
| `PATCH/DELETE /api/customer-intelligence/schedules/{id}` | Versioned update/disable |

Create trusted rule UI phải hiển thị action, sender/domain, target connection, threshold, daily cap và expiry. Không cung cấp rule “mọi sender”.

### 12.7 Error contract

API errors dùng cấu trúc ổn định:

```json
{
  "error": {
    "code": "PROPOSAL_VERSION_CONFLICT",
    "message": "Proposal changed; reload before deciding.",
    "correlation_id": "uuid",
    "retryable": false
  }
}
```

Không trả provider response thô, stack trace, token hoặc decrypted payload trong error.

## 13. Classification và policy defaults

### 13.1 Threshold mặc định

| Route | Dispatch threshold | Below threshold |
|---|---:|---|
| Spam ignore | 0.95 | Summary/uncertain notification |
| Calendar proposal | 0.80 và đủ start/end/timezone | Notify user, không proposal |
| Customer research | 0.75 và có company/domain candidate | Summary + “research suggested” |
| Security quarantine | Guard quyết định, không dùng LLM confidence | Metadata-only review |

Threshold cấu hình theo organization nhưng user rule chỉ được làm chặt hơn security baseline, không được hạ guard restriction.

### 13.2 Time extraction

- Dùng timezone explicit trong email nếu hợp lệ.
- Nếu thiếu, dùng timezone profile user.
- Relative date được resolve theo email `received_at`, không theo thời điểm worker chạy.
- Ambiguous date/time hoặc missing timezone không đủ điều kiện auto-create.
- All-day event phải được classifier đánh dấu rõ, không suy từ `00:00`.
- Calendar proposal lưu cả original text span hash và normalized UTC value để audit mà không log raw body.

### 13.3 Spam handling

Version đầu chỉ đánh dấu nội bộ `IGNORED` và có thể đề xuất Gmail label/archive. Không tự trash hoặc permanent delete. User có thể xem lý do và restore processing bằng reprocess action.

## 14. Research/report requirements

Report canonical gồm đúng bảy section:

1. Executive Summary.
2. Company Overview.
3. Recent News.
4. Contact Information.
5. Upcoming Meetings.
6. Open Questions.
7. Sources.

Source record phải có URL canonical, title, publisher, published date, retrieved date, excerpt hash, source type và confidence. URL dedupe sau normalization; tracking parameter phổ biến bị loại. Tin “recent” mặc định trong 30 ngày.

Web fetch policy:

- chỉ `http`/`https`;
- resolve DNS và block private/loopback/link-local/metadata IP cho IPv4/IPv6;
- re-check từng redirect, tối đa 3 redirect;
- giới hạn response bytes và timeout;
- không gửi cookie hoặc OAuth credential;
- crawler container không được truy cập host network hoặc Docker socket;
- domain từ email ở `restricted` không được fetch trực tiếp nếu chưa được verified bằng safe search result.

Nếu search/company/calendar provider thiếu dữ liệu, report dùng explicit warning; không sinh claim không có provenance.

## 15. Google OAuth và Pub/Sub production setup

### 15.1 Google Cloud projects

Tạo project riêng cho development/staging và production. Production dùng domain do chủ hệ thống sở hữu, HTTPS, public home page, privacy policy, terms/support contact và OAuth consent branding khớp thực tế.

Vì hệ thống hỗ trợ Gmail cá nhân ngoài một Workspace nội bộ, release public phải hoàn tất verification áp dụng cho sensitive/restricted scopes. Nếu restricted Google user data được lưu hoặc truyền qua server, kế hoạch release phải tính cả security assessment mà Google yêu cầu. Scope classification phải kiểm tra lại trong Google Cloud Console tại thời điểm submit.

### 15.2 Incremental scopes

Không xin toàn bộ scope ngay lần đầu. Scope được xin khi user bật feature:

| Feature | Scope mục tiêu |
|---|---|
| Đọc/phân tích Gmail | `https://www.googleapis.com/auth/gmail.readonly` |
| Label/archive | `https://www.googleapis.com/auth/gmail.modify` |
| Tạo draft | `https://www.googleapis.com/auth/gmail.compose` |
| Gửi email | `https://www.googleapis.com/auth/gmail.send` |
| Đọc/tạo Calendar event | `https://www.googleapis.com/auth/calendar.events` |
| Lưu file app tạo vào Drive | `https://www.googleapis.com/auth/drive.file` |

Không dùng scope toàn quyền `https://mail.google.com/` nếu endpoint cần thiết hoạt động với scope hẹp hơn. Sau OAuth callback, lưu granted scopes thực tế và disable action thiếu scope.

### 15.3 Credential handling

- OAuth client secret và application encryption master key được mount qua Compose secrets/read-only files, không commit `.env`.
- Refresh token được AES-256-GCM authenticated-encrypt với nonce riêng và key version.
- Access token ưu tiên giữ trong memory ngắn hạn; nếu cache Redis thì phải encrypt và TTL ngắn.
- Không log authorization code, access token, refresh token hoặc raw provider error body có token.
- Disconnect cố gắng revoke provider token, stop watch, xóa encrypted credential và audit outcome.
- Key rotation decrypt bằng old key ID rồi re-encrypt bằng active key theo batch có audit.

### 15.4 Pub/Sub

- Gmail API publish vào topic production riêng.
- Push subscription bật authenticated push bằng service account riêng.
- Webhook verify Google-signed OIDC JWT, exact audience, expected service-account email, issuer, expiry và issued-at tolerance.
- Pub/Sub retry duplicate là expected behavior; endpoint phải idempotent.
- Webhook chỉ expose qua Caddy HTTPS và có request-size/rate protections.
- Alert nếu push authentication failure tăng hoặc không có notification trong khi reconciliation vẫn thấy email mới.

### 15.5 Gmail watch lifecycle

Gmail yêu cầu renew mailbox watch ít nhất mỗi 7 ngày và tài liệu khuyến nghị gọi hằng ngày. Scheduler kiểm tra mỗi 12 giờ, renew khi expiration dưới 48 giờ, ghi expiration provider trả về và alert dưới 24 giờ. Connect/reconnect phải gọi watch ngay sau khi token/scopes được xác nhận.

## 16. Security controls

### 16.1 Multi-tenant và ownership

- Repository/service bắt buộc nhận `org_id` và owner scope.
- User role chỉ query own Gmail, Calendar, Drive, email, case, report, proposal và approval.
- Admin chỉ xem metadata vận hành của mailbox cá nhân mặc định; content access cần policy và audit riêng.
- Shared connection có explicit scope/membership ACL.
- Download blob và decrypt content luôn kiểm tra ownership tại thời điểm request.
- Background worker reload owner từ DB trước mỗi provider/LLM call.

### 16.2 Prompt injection

- Email body được delimit dưới role/data field, không nối vào system instruction.
- Tool/action capability không xuất hiện trong classifier agent.
- Classifier output schema không có execute fields.
- Guard flags đi vào deterministic router.
- `restricted` vô hiệu trusted-rule auto execution.
- Research fetch không làm theo instruction nằm trong web page.
- Security harness phải chứa injection đa ngôn ngữ, encoded content, HTML hidden text và attachment text.

### 16.3 Attachment

- Giới hạn mặc định 10 MiB/attachment và 25 MiB tổng/email; cấu hình chỉ được giảm hoặc tăng trong giới hạn vận hành đã benchmark.
- Extension không quyết định an toàn; detected MIME và scanner result mới quyết định access.
- Archive recursion/decompression ratio có giới hạn chống zip bomb.
- Attachment ở quarantine bucket cho đến `clean`.
- ClamAV timeout/failure fail closed cho attachment access.
- Infected object bị cô lập, không đưa vào LLM/crawler và xóa theo security retention policy.

### 16.4 URL/SSRF

- Block RFC1918, loopback, link-local, multicast, IPv6 local và cloud metadata endpoint.
- Resolve hostname trước request và lại sau redirect.
- Chống DNS rebinding bằng cách pin resolved public IP cho connection.
- Chỉ allow port 80/443 mặc định.
- Crawler chạy network policy riêng, không mount Docker socket, host filesystem hoặc secret directory.
- Request không forward arbitrary header/cookie từ email.

### 16.5 LLM cloud data policy

- Chỉ provider được admin allowlist và có API data policy phù hợp mới được dùng.
- Gửi minimum necessary content sau Guard/DLP.
- Không gửi attachment nếu chưa clean và route không cần attachment.
- Model request gắn purpose, policy version và content hash; không log raw content mặc định.
- Langfuse/OTel content capture production mặc định off cho Gmail body; chỉ metadata, token count, latency, model ID và hash.
- User có trang disconnect/delete data và retention disclosure.

### 16.6 Approval/replay

- Approval bind proposal ID/version, payload hash, scope, target connection và expiry.
- Decision actor lấy từ authenticated session.
- Approval replay sau edit/expiry bị từ chối.
- Trusted rule snapshot immutable và daily cap atomically enforced.
- Executor revalidate toàn bộ precondition ngay trước atomic claim.
- Audit log append-only cho proposal create/edit, approve/reject/cancel, executor claim, provider attempt và manual resolution.

## 17. Notifications và UX requirements

### 17.1 Inbox Intelligence UI

Mỗi email row hiển thị sender, subject, received time, classifier labels, aggregate status, guard warning và unread state. `ROUTING_COMPLETED` không được hiển thị thành “Completed” nếu child workflow còn chạy.

### 17.2 Review surfaces

- Calendar proposal hiển thị timezone, original extracted phrase, normalized time, attendees, confidence và uncertain fields.
- Customer report hiển thị 7 sections, warning, confidence và clickable source.
- Action approval hiển thị exact recipient/target, payload diff so với version trước, expiry, risk và trusted-rule match.
- Manual review hiển thị provider, attempt timeline, trạng thái mơ hồ, read-only reconciliation result và ba terminal resolution an toàn.

### 17.3 User control

- User có thể disable realtime processing theo connection.
- User có thể chỉnh daily digest timezone/schedule.
- User có thể tạo, disable và xem hit history của trusted rule.
- User có thể cancel research đang chạy và proposal chưa execute.
- User có thể yêu cầu xóa dữ liệu theo retention/privacy policy; xóa connection không mặc nhiên xóa audit bắt buộc nhưng phải redact content theo policy.

## 18. Observability và audit

### 18.1 Correlation

Một `correlation_id` theo luồng notification → email → guard → classification → route → case/proposal → execution. Mỗi event có `causation_id`. Log chỉ chứa ID đã cho phép, reason code và hash; không chứa email body/token.

### 18.2 Metrics

```text
gmail_webhook_requests_total
gmail_webhook_auth_failures_total
gmail_watch_expiry_seconds
gmail_checkpoint_lag
email_stage_duration_seconds
guard_outcomes_total
classifier_schema_failures_total
routing_decisions_total
outbox_pending_total
outbox_oldest_age_seconds
queue_depth
queue_oldest_age_seconds
worker_job_duration_seconds
worker_job_failures_total
provider_rate_limit_total
provider_ambiguous_write_total
research_duration_seconds
research_partial_total
approval_age_seconds
manual_review_age_seconds
dead_letter_total
scheduler_lag_seconds
lease_recovery_total
```

Metric label không chứa email address, subject, domain tùy ý hoặc user-controlled high-cardinality string.

### 18.3 Alerts

- Gmail watch dưới 24 giờ.
- Outbox oldest age trên 60 giây.
- Ingest/classify queue oldest age trên 60 giây.
- Classification p95 trên 60 giây.
- Research p95 trên 3 phút.
- Action ở `EXECUTING` quá timeout.
- `MANUAL_REVIEW` trên 24 giờ.
- Dead-letter mới xuất hiện.
- PostgreSQL backup quá 24 giờ hoặc restore verification fail.
- Disk trên 80%, MinIO object deletion backlog hoặc ClamAV unavailable.

### 18.4 Audit retention

Audit event chứa actor, org, user owner, action, resource ID/version, decision, reason code, timestamp, IP/session ID khi có và correlation ID. Audit payload không chứa secret/raw body. Retention audit mặc định 365 ngày; email body/report mặc định 30 ngày; attachment mặc định 14 ngày. Organization có thể cấu hình ngắn hơn, hoặc dài hơn khi có policy pháp lý rõ ràng.

## 19. Docker Compose production deployment

### 19.1 VPS sizing ban đầu

- 4 vCPU, 8 GiB RAM là mức tối thiểu để chạy API, worker, PostgreSQL, Redis, ClamAV và crawler có kiểm soát.
- 8 vCPU, 16 GiB RAM được khuyến nghị khi Crawl4AI chạy thường xuyên.
- SSD 100 GiB trở lên, theo dõi growth của PostgreSQL/MinIO.
- Swap nhỏ chỉ để chống OOM tức thời; không dùng swap để bù thiếu RAM kéo dài.

### 19.2 Network exposure

Chỉ publish:

- TCP 80/443 cho Caddy;
- SSH theo firewall allowlist/VPN quản trị.

PostgreSQL, Redis, MinIO console, ARQ worker, ClamAV, SearXNG, crawler và observability backend chỉ nằm trong private Compose network. Grafana nếu expose phải qua Caddy và authentication.

### 19.3 Container hardening

- Pin image version/digest; không dùng floating `latest` trong production.
- Chạy non-root khi image hỗ trợ.
- Read-only root filesystem và tmpfs cho temp path khi khả thi.
- Drop Linux capabilities không cần thiết.
- Resource limit cho crawler/ClamAV/worker.
- `restart: unless-stopped` và healthcheck phù hợp.
- Không mount Docker socket vào API/worker/crawler. Docker socket proxy hiện có không được mở rộng quyền cho feature này.
- Secrets mount read-only; `.env` production permission tối thiểu và không commit.

### 19.4 PostgreSQL/Redis/MinIO durability

- Named volume nằm ngoài source checkout.
- Không dùng `docker compose down -v` trong runbook production.
- Redis bật AOF và `maxmemory-policy=noeviction`; queue vẫn rebuild từ PostgreSQL.
- PostgreSQL backup hằng ngày ra remote encrypted storage, giữ 7 daily, 4 weekly, 6 monthly.
- MinIO backup theo object retention; PostgreSQL metadata và MinIO snapshot phải có cùng backup epoch hoặc reconciliation manifest.
- Restore drill mỗi tháng trên môi trường tách biệt.
- Mục tiêu ban đầu: RPO 24 giờ, RTO 4 giờ.

### 19.5 Graceful shutdown

Worker ngừng claim job mới khi SIGTERM, có 30 giây hoàn tất/checkpoint. Job chưa hoàn tất để lease expire và resume từ PostgreSQL. Deploy API/worker không được chạy migration đồng thời từ nhiều container; một migration job thực hiện trước rollout.

## 20. Test strategy

### 20.1 Unit tests

- JSON Schema/Pydantic `extra=forbid` cho mọi contract.
- State transition allow/deny table.
- Guard routing matrix đủ 4 outcome × route.
- Canonical JSON hashing và proposal version invalidation.
- UUIDv5 idempotency key ổn định.
- Timezone, relative time và DST.
- Backoff/full jitter trong bounds.
- URL/IP/redirect/SSRF validator.
- DLP redaction không log raw evidence.

### 20.2 Database integration tests

- Outbox write cùng transaction với aggregate.
- Hai dispatcher cạnh tranh chỉ claim bằng `SKIP LOCKED`.
- Duplicate outbox delivery chỉ process một lần mỗi consumer.
- Hai Gmail sync cùng connection chỉ một lease thắng.
- Checkpoint không advance khi một email trong batch chưa persist.
- User cancel vs research finalize có đúng một CAS winner.
- Proposal cancel vs executor claim có đúng một CAS winner.
- Approval payload hash/version mismatch bị invalidated.
- Cross-org/cross-user query trả 404/403 theo API policy và không lộ existence.

### 20.3 Provider contract tests

Dùng fake deterministic provider cho CI:

- Gmail duplicate notification và overlapping history range.
- Gmail 401 refresh một lần, `invalid_grant` chuyển reauth.
- Gmail send success nhưng response timeout, reconciliation tìm thấy Sent.
- Gmail ambiguous result không resend.
- Calendar insert timeout rồi duplicate event ID lookup.
- Calendar payload mismatch chuyển manual review.
- Company/search/calendar branch unavailable tạo partial report.
- Pub/Sub duplicate push trả `204` và một notification row.

### 20.4 Security Harness

- Prompt injection trong plain text, HTML hidden text, base64-like text và attachment.
- Email yêu cầu tiết lộ API key không làm lộ secret hoặc tạo tool action.
- Malicious URL, redirect tới private IP, DNS rebinding và metadata endpoint.
- MIME mismatch, zip bomb, oversized attachment và ClamAV timeout.
- Queue payload giả org/user không vượt ownership reload.
- Approval expired, replayed, edited proposal và payload hash mismatch.
- Trusted rule restricted outcome không auto-execute.
- Log/trace scan không chứa access token, refresh token, email body hoặc known fixture secret.

### 20.5 Evaluation Harness

Fixtures FPT Software, Vinamilk, Samsung Vietnam, Shopee Vietnam, Viettel Solutions và Bosch. Assert:

- company identity đúng;
- đủ 7 report sections;
- source không trùng và claim có provenance;
- news trong lookback window;
- calendar matching đúng;
- provider thiếu dữ liệu không hallucinate;
- spam không tạo research/action;
- normal email tạo summary notification;
- calendar email tạo proposal đúng timezone;
- approval reject không side effect;
- retry không duplicate side effect.

Automated test không gọi production Gmail, production database, LLM thật hoặc gửi email thật.

### 20.6 Load/chaos tests

- Burst 1.000 Pub/Sub notifications, duplicate 20%, webhook p95 dưới 500 ms khi PostgreSQL khỏe.
- 100 connections reconciliation cùng tick, per-connection lease giữ đúng.
- Kill worker giữa normalize, research và action reconciliation; state resume đúng stage.
- Restart Redis/AOF; outbox rebuild queue không mất aggregate.
- Redis unavailable trong 5 phút; webhook persist-only và recover sau khi Redis lên.
- Provider 429 trong 15 phút; backlog không làm nghẽn webhook.
- PostgreSQL failover không nằm trong single-VPS scope, nhưng process phải fail closed và recover khi DB trở lại.

## 21. Acceptance criteria

Feature chỉ được coi là production-ready khi:

1. Gmail push và reconciliation ingest cùng email không tạo duplicate.
2. Webhook không gọi Gmail/LLM và trả p95 dưới 500 ms trong load target.
3. Phân loại/notification p95 dưới 60 giây.
4. Research/report p95 dưới 3 phút với fixture provider bình thường.
5. Report có 7 sections, provenance và missing-data warning.
6. `restricted` không auto-execute trusted rule.
7. Quarantine/reject không gửi body/attachment tới LLM.
8. Calendar/email/KB write không xảy ra nếu approval/rule invalid.
9. Edit proposal làm approval cũ vô hiệu.
10. Crash/retry không tạo duplicate Calendar event hoặc email send trong deterministic tests.
11. Ambiguous Gmail/KB write không resend mù và xuất hiện ở Manual Review.
12. Cross-user/cross-tenant tests pass.
13. Secret scan trên logs/traces pass.
14. Outbox/queue recovery pass khi Redis restart.
15. Backup artifact được restore thành công trong drill.
16. Google OAuth production prerequisites hoàn tất trước khi mở cho Gmail cá nhân ngoài test-user list.

## 22. Rollout phases

### Phase 0 — Foundation

- Additive migrations, outbox, processed event, queue split, scheduler-dispatcher.
- Feature flags toàn cục, organization và user.
- Không bật provider side effect.

### Phase 1 — Read-only inbox intelligence

- Gmail OAuth readonly, Pub/Sub watch, reconciliation, normalize/guard/classify.
- Summary notification và spam/internal ignore.
- Không Calendar/Gmail/KB write.

### Phase 2 — Customer research

- Automatic customer routing, SearXNG/Crawl4AI/company/calendar read.
- Report 7 sections và provenance.
- Manual research dùng chung pipeline.

### Phase 3 — Calendar proposals

- Calendar event extraction, proposal, explicit approval và idempotent insert.
- Trusted rules vẫn disabled trong canary đầu.

### Phase 4 — Gmail/KB actions và trusted rules

- Draft/send split, reconciliation/manual review.
- Knowledge save.
- Trusted rules theo sender/domain với daily cap và expiry.

### Phase 5 — Production hardening

- Load/chaos/security/evaluation harness đạt acceptance.
- Dashboard/alerts, retention, remote backup và restore drill.
- Google OAuth verification/security assessment phù hợp scope.

Mỗi phase có feature flag và rollback bằng cách dừng dispatch mới; không rollback migration destructive. In-flight action được reconcile trước khi disable executor.

## 23. Compatibility với code hiện tại

Phần có thể tái sử dụng:

- FastAPI auth/RBAC và user-owned Google connections;
- PostgreSQL/Redis/ARQ worker;
- `run_leased_tick` và `job_schedule_executions`;
- Customer Intelligence research providers, report renderer và source model;
- approval/audit/metrics infrastructure;
- SearXNG, Crawl4AI, MinIO và observability stack.

Phần phải thay đổi có chủ đích:

- chuyển Gmail ingestion thành push + durable outbox;
- thêm Normalize/Guard/Classifier/Router pipeline;
- tách queue/worker service theo workload;
- đổi research API sang enqueue-only;
- tách `ActionExecution` khỏi N `DeliveryAttempt`;
- thêm proposal version/hash/scope và manual review;
- thay case-level delivery coupling bằng lifecycle action độc lập;
- thêm aggregate UI status và personal inbox intelligence screens;
- bỏ plaintext-sensitive content path trong production.

## 24. Production configuration keys

Các key mới dùng prefix `OPENAGENT_`:

```text
OPENAGENT_PUBLIC_BASE_URL
OPENAGENT_GOOGLE_PUBSUB_AUDIENCE
OPENAGENT_GOOGLE_PUBSUB_SERVICE_ACCOUNT_EMAIL
OPENAGENT_GOOGLE_PUBSUB_TOPIC
OPENAGENT_CI_GMAIL_RECONCILE_SECONDS=300
OPENAGENT_CI_GMAIL_WATCH_RENEW_BEFORE_SECONDS=172800
OPENAGENT_CI_OUTBOX_POLL_SECONDS=1
OPENAGENT_CI_OUTBOX_BATCH_SIZE=100
OPENAGENT_CI_INGEST_CONCURRENCY=4
OPENAGENT_CI_CLASSIFY_CONCURRENCY=4
OPENAGENT_CI_RESEARCH_CONCURRENCY=2
OPENAGENT_CI_ACTION_CONCURRENCY=2
OPENAGENT_CI_MAX_PENDING_RESEARCH_PER_USER=20
OPENAGENT_CI_MAX_CONCURRENT_RESEARCH_PER_USER=2
OPENAGENT_CI_EMAIL_RETENTION_DAYS=30
OPENAGENT_CI_ATTACHMENT_RETENTION_DAYS=14
OPENAGENT_CI_AUDIT_RETENTION_DAYS=365
OPENAGENT_CLAMAV_HOST=clamav
OPENAGENT_CLAMAV_PORT=3310
OPENAGENT_CREDENTIAL_ENCRYPTION_KEY_FILE=/run/secrets/credential_encryption_key
OPENAGENT_CONTENT_ENCRYPTION_KEY_FILE=/run/secrets/content_encryption_key
```

Production startup fail closed nếu thiếu JWT secret, credential/content encryption key, PostgreSQL password, crawler token hoặc Google credentials cho feature đã enable. Development defaults không được chấp nhận khi `OPENAGENT_RUNTIME=production`.

## 25. Official external references

- [Gmail API push notifications and watch renewal](https://developers.google.com/workspace/gmail/api/guides/push)
- [Gmail users.watch reference](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users/watch)
- [Authenticated Pub/Sub push subscriptions](https://docs.cloud.google.com/pubsub/docs/authenticate-push-subscriptions)
- [Pub/Sub push delivery and redelivery](https://docs.cloud.google.com/pubsub/docs/push)
- [Google OAuth 2.0 policies](https://developers.google.com/identity/protocols/oauth2/policies)
- [OAuth production readiness and policy compliance](https://developers.google.com/identity/protocols/oauth2/production-readiness/policy-compliance)
- [Restricted scope verification](https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification)
- [Sensitive scope verification](https://developers.google.com/identity/protocols/oauth2/production-readiness/sensitive-scope-verification)
- [Google OAuth incremental authorization guidance](https://developers.google.com/identity/protocols/oauth2)
- [Google Calendar create events and client-generated IDs](https://developers.google.com/workspace/calendar/api/guides/create-events)
- [Google Calendar events.insert reference](https://developers.google.com/workspace/calendar/api/v3/reference/events/insert)
