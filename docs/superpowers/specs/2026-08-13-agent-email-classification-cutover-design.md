# Agent-based Email Classification and Clean Cutover — Production Specification

> Ngày: 2026-08-13
> Trạng thái: Spec đã chốt, chờ user review trước khi viết implementation plan
> Target: Docker Compose/VPS, dưới 100 user
> Phạm vi: Gmail cá nhân và Google Workspace
> Tài liệu nền: `docs/superpowers/specs/2026-08-13-personal-email-intelligence-automation-design.md`

## 1. Bối cảnh và lỗi hiện tại

Pipeline hiện tại dùng classifier rule-based. Một rule coi gần như mọi sender có domain không thuộc nhóm email miễn phí là `customer`. Hệ quả là newsletter, thông báo hệ thống, email marketing và transactional mail từ các domain như GitHub, Google, Vercel hoặc nhà cung cấp SaaS bị tạo thành `ResearchCase`.

Khi company matching không tìm thấy công ty, workflow vẫn tạo `REPORT_READY` với nội dung “No company matched”, “No sources” và UI hiển thị tên fallback `Unmatched sender`. Đây là dữ liệu sai do pipeline tạo ra, không phải research report có giá trị.

Spec này thay classifier rule-based bằng Classification Agent có output schema chặt chẽ. Rule/code chỉ còn chịu trách nhiệm bảo mật, quota, threshold, routing và side-effect policy. Spec đồng thời định nghĩa cutover một lần: xóa dữ liệu intelligence sai, coi email cũ là đã xử lý và chỉ phân tích email mới nhận từ thời điểm cutover.

## 2. Mục tiêu

### 2.1 Mục tiêu chức năng

- Mọi email mới sau cutover được agent đọc và phân loại theo ngữ nghĩa.
- Phân biệt tối thiểu: `spam`, `marketing`, `newsletter`, `transactional`, `system`, `normal`, `customer`, `partner`, `calendar`, `security_risk`, `uncertain`.
- Chỉ tạo `ResearchCase` khi có customer/partner intent và company signal đạt threshold.
- Chỉ tạo Calendar proposal khi meeting intent và dữ liệu thời gian đạt threshold.
- Email bình thường chỉ tạo Smart Inbox notification và summary.
- Email marketing/newsletter/system/transactional không tạo research report.
- Email không chắc chắn được escalation hoặc đưa vào review; hệ thống không đoán bằng rule.
- Email cũ trước cutover không được reclassify hoặc quét lại sau restart.

### 2.2 Mục tiêu latency và cost

- Webhook p95 dưới 500 ms và không gọi LLM inline.
- Email mới vào classification queue p95 dưới 2 giây sau khi ingest commit.
- Classification + routing p95 dưới 10 giây ở tải bình thường.
- Escalation sang model mạnh dưới 10% workload chuẩn.
- Input first-pass trung bình không quá 1.500 token/email.
- Output classification không quá 180 token/email.
- Classification cost mục tiêu mặc định không quá 0,50 USD/1.000 email, có thể cấu hình theo provider/model.
- Chỉ customer/calendar đã vượt threshold mới tạo workload research/action đắt tiền.

### 2.3 Mục tiêu an toàn và tính đúng

- Email body, attachment và website luôn là untrusted data.
- Guard chạy trước mọi LLM call.
- LLM chỉ trả dữ liệu; không được gọi tool, tạo lịch, gửi email hoặc tạo case trực tiếp.
- Policy Router deterministic là thành phần duy nhất quyết định route.
- Không tạo report “rỗng” khi không xác định được company.
- Retry, push trùng và reconciliation không gọi LLM hoặc tạo case trùng.
- Cutover không làm mất email mới đến trong lúc vận hành.
- Audit không lưu access token, secret hoặc raw email body.

## 3. Ngoài phạm vi

- Quét và phân loại lại mailbox cũ.
- Tự động gửi email không qua approval/trusted policy.
- Dùng rule domain làm bằng chứng đủ để kết luận customer.
- Dùng embedding/vector database trong phase đầu.
- Fine-tune model trong phase đầu.
- Kafka, RabbitMQ, Temporal hoặc Kubernetes cho target dưới 100 user.
- Xóa Gmail message khỏi mailbox của user.

## 4. Quyết định kiến trúc

### 4.1 Agent cascade

Chọn mô hình cascade hai tầng:

1. Economy Classification Agent đọc mọi email mới đã qua Guard.
2. Strong Classification Agent chỉ xử lý email có confidence trung bình, output mâu thuẫn hoặc schema repair thất bại.
3. Deterministic Policy Router áp threshold, Guard Decision, quota và user policy.
4. Research Agent chỉ chạy cho route `customer_research` đã được Router chấp nhận.

Không chọn một model mạnh cho mọi email vì cost và latency cao. Không chọn rule/embedding làm classifier chính vì đó là nguyên nhân tạo report rác hiện tại.

### 4.2 Nền tảng

| Thành phần | Lựa chọn |
|---|---|
| Canonical state | PostgreSQL |
| Execution transport | Redis 7 + ARQ |
| Durable dispatch | PostgreSQL outbox + processed-event dedupe |
| Scheduler | ARQ cron + PostgreSQL lease |
| Model access | Model/Provider catalog và OpenAI-compatible LLM client hiện có |
| Economy/strong model | Cấu hình theo environment/org; không hardcode vendor |
| Metrics | Prometheus + Grafana |
| Trace | OpenTelemetry + Langfuse metadata-only trong production |

PostgreSQL là nguồn sự thật. Queue payload chỉ chứa ID, generation và correlation ID. Worker luôn reload ownership/state từ database.

## 5. Luồng tổng thể

```text
Gmail Pub/Sub / reconciliation
  → Gmail History incremental sync
  → Normalize MIME
  → Guard
  → persist InboundEmail
  → transactional outbox: email.classification.requested
  → ci:classify
  → Economy Classification Agent
       ├─ valid + confident → classification accepted
       └─ ambiguous/invalid → ci:classify-escalation
                              → Strong Classification Agent
  → Deterministic Policy Router
       ├─ spam/marketing/newsletter/system/transactional → archive decision only
       ├─ normal → Smart Inbox summary notification
       ├─ customer/partner → ResearchCase + ci:research
       ├─ calendar → ActionProposal + approval/trusted-rule evaluation
       ├─ security_risk → quarantine/restricted
       └─ uncertain → Needs Review
```

Webhook không tải email, không gọi LLM và không đợi Redis. Restart API/worker không chạy mailbox full scan. Gmail `historyId` là durable checkpoint.

## 6. Normalize và tối ưu input

Trước classification, hệ thống tạo `ClassificationInput` từ bản normalized canonical:

- giữ sender name/address/domain và authentication results;
- giữ subject;
- giữ phần text mới nhất của email;
- loại quoted thread, forwarded history lặp, signature phổ biến, tracking URL và invisible HTML;
- HTML được chuyển sang text an toàn, không tải remote image;
- attachment chỉ truyền metadata và text đã scan/allow nếu policy cho phép;
- URL chỉ truyền hostname và safe normalized URL khi cần;
- body được truncate theo token budget, không truncate mù theo ký tự;
- ưu tiên đầu email, câu chứa company/meeting intent và phần cuối không phải signature;
- prompt injection flags được truyền như security context, không phải instruction.

Budget mặc định:

| Thành phần | Giới hạn |
|---|---:|
| Subject | 500 ký tự |
| Sender/display/auth metadata | 1.000 ký tự |
| Clean body | tối đa 6.000 ký tự hoặc token cap thấp hơn |
| Attachment extracted text | tối đa 1.500 token tổng |
| Tổng economy input | hard cap 2.000 token/email |
| Economy output | hard cap 180 token/email |
| Strong input | hard cap 3.500 token/email |
| Strong output | hard cap 240 token/email |

Không gửi raw HTML, tracking query string hoặc toàn bộ quoted conversation nếu không cần thiết.

## 7. Classification Agent contract

### 7.1 Input

```json
{
  "schema_version": "email-classification-input.v1",
  "email_id": "uuid",
  "content_revision": 1,
  "sender": {
    "name": "Sales Team",
    "email": "sales@example.com",
    "domain": "example.com",
    "authentication": {
      "spf": "pass",
      "dkim": "pass",
      "dmarc": "pass"
    }
  },
  "subject": "Meeting to discuss enterprise deployment",
  "body_text": "...bounded clean text...",
  "attachments": [
    {
      "filename": "agenda.pdf",
      "content_type": "application/pdf",
      "size_bytes": 120000,
      "scan_status": "clean"
    }
  ],
  "received_at": "2026-08-13T10:00:00Z",
  "security_context": {
    "guard_outcome": "pass",
    "prompt_injection_flags": [],
    "unsafe_url_flags": [],
    "redactions_applied": []
  }
}
```

### 7.2 Output

```json
{
  "schema_version": "email-classification-result.v1",
  "mail_type": "business",
  "primary_label": "customer",
  "intents": ["customer_or_partner", "meeting_request"],
  "summary": "A prospective customer requests a deployment meeting.",
  "company": {
    "name": "Example Corporation",
    "domain": "example.com",
    "confidence": 0.93,
    "evidence": ["sender_domain", "email_body"]
  },
  "calendar": {
    "has_event_request": true,
    "confidence": 0.91,
    "start": "2026-08-15T03:00:00Z",
    "end": "2026-08-15T04:00:00Z",
    "timezone": "Asia/Bangkok",
    "attendees": ["sales@example.com"],
    "missing_fields": []
  },
  "recommended_routes": [
    "notify",
    "customer_research_candidate",
    "calendar_proposal_candidate"
  ],
  "confidence": 0.92,
  "reason_codes": ["BUSINESS_INTENT", "COMPANY_IDENTIFIED", "MEETING_REQUEST"]
}
```

### 7.3 Enum

`primary_label`:

```text
spam | marketing | newsletter | transactional | system | normal |
customer | partner | calendar | security_risk | uncertain
```

`mail_type`:

```text
business | personal | automated | promotional | suspicious | unknown
```

Classifier schema không có field `execute`, `send`, `create`, `tool`, `approval` hoặc provider credential.

### 7.4 Validation

- Pydantic/JSON Schema dùng `extra=forbid`.
- Unknown enum, thiếu required field hoặc confidence ngoài `[0,1]` là invalid.
- Output phải chứa đúng một result cho mỗi input email ID.
- Model không được thay đổi `email_id` hoặc `content_revision`.
- Invalid output được repair tối đa một lần; sau đó escalation.
- Strong model vẫn invalid thì chuyển `NEEDS_REVIEW`, không fallback sang rule đoán.

## 8. Dynamic batching

Classifier worker gom tối đa 8 email trong tối đa 250 ms, chỉ gom email cùng `org_id`, `user_id`, Guard class và data policy. Tổng batch không vượt token budget provider.

Batch contract delimit từng email độc lập và output là array keyed theo `email_id`. Không trộn email khác tenant/user trong cùng prompt. Nếu thiếu hoặc invalid một item, chỉ item đó được retry/escalate; item hợp lệ vẫn được commit.

Provider không hỗ trợ hoặc không có lợi từ multi-item request thì worker giữ micro-batch ở tầng scheduler nhưng gọi song song từng email với shared concurrency/rate limiter. Offline Batch API có SLA nhiều giờ không được dùng cho realtime classification.

## 9. Cache và idempotency

Cache key canonical:

```text
sha256(
  org_data_policy_version |
  content_hash |
  content_revision |
  guard_decision_hash |
  prompt_version |
  output_schema_version |
  model_id
)
```

Cache lưu trong PostgreSQL classification result; Redis có thể giữ hot lookup nhưng không phải nguồn sự thật.

Invariant:

- Retry cùng cache key không gọi LLM lại.
- Thay prompt/model/schema/guard revision tạo cache key mới.
- Một email chỉ có một accepted classification cho mỗi content revision.
- Router chỉ nhận accepted classification có hash khớp email revision hiện tại.
- Một automatic `ResearchCase` tối đa trên một email.
- Outbox và consumer dedupe ngăn double dispatch.

## 10. State machines

### 10.1 Email processing

```text
RECEIVED
→ NORMALIZED
→ GUARDED
→ CLASSIFY_QUEUED
→ CLASSIFYING
→ CLASSIFIED
→ ROUTED
→ PROCESSED
```

Nhánh lỗi:

```text
CLASSIFYING → RETRY_SCHEDULED → CLASSIFYING
CLASSIFYING → ESCALATION_QUEUED → CLASSIFYING
CLASSIFYING → NEEDS_REVIEW
CLASSIFYING → DEAD_LETTER
```

Email trước cutover:

```text
* → HISTORICAL_SKIPPED
```

`PROCESSED` chỉ là terminal của email classification/routing. Research, approval và execution có lifecycle độc lập.

### 10.2 Classification attempt

```text
CREATED → RUNNING → SUCCEEDED
RUNNING → INVALID_OUTPUT | PROVIDER_FAILED | TIMED_OUT
INVALID_OUTPUT → REPAIRING → SUCCEEDED | ESCALATED
PROVIDER_FAILED/TIMED_OUT → RETRY_SCHEDULED → RUNNING
```

### 10.3 Cutover

```text
REQUESTED → PREVIEWED → QUEUED → RUNNING → COMPLETED
RUNNING → FAILED
FAILED → QUEUED
```

Cutover retry dùng cùng idempotency key/generation và không xóa hoặc advance checkpoint hai lần.

## 11. Deterministic Policy Router

Classifier đề xuất route; Router quyết định route thật.

| Agent result | Điều kiện mặc định | Router action |
|---|---|---|
| spam/marketing/newsletter/system/transactional | label confidence ≥ 0,80 | Không tạo case; có thể notify theo user preference |
| normal | confidence ≥ 0,75 | Smart Inbox summary |
| customer/partner | intent ≥ 0,85; company ≥ 0,75; Guard pass/restricted | Tạo ResearchCase; restricted gắn warning |
| calendar | meeting intent ≥ 0,85; thời gian đủ dữ liệu | Tạo Calendar proposal |
| security_risk | Guard/policy quyết định | Quarantine/restricted; không auto-action |
| uncertain | dưới threshold sau economy | Escalate strong model |
| uncertain sau strong | vẫn dưới threshold | Needs Review; không tạo case |

Domain tổ chức, `noreply`, unsubscribe header, SPF/DKIM/DMARC, contact history và Gmail category chỉ là feature/evidence. Không feature nào được tự kết luận customer hoặc spam.

Security policy luôn có quyền hạ route. Trusted rule không được nâng `uncertain` thành customer hoặc bỏ qua Guard.

Router ghi trong một transaction:

1. immutable `EmailRoutingDecision`;
2. child aggregate cần thiết;
3. outbox event;
4. email status `ROUTED/PROCESSED`;
5. commit.

## 12. Không tạo report rỗng

Automatic customer research chỉ bắt đầu khi Router đã xác nhận customer/company signal. Sau research:

- Có company và nguồn hợp lệ: tạo report.
- Company provider tạm lỗi: case `RETRYING`, không tạo report rỗng.
- Không match company sau provider thành công: case `RESEARCH_UNAVAILABLE` hoặc `NEEDS_REVIEW`.
- Không nguồn web/news nhưng company đã xác định: report có thể tạo với warning nếu có đủ official/company data.
- Không company và không nguồn: tuyệt đối không chuyển `REPORT_READY`.

UI Research Cases mặc định chỉ hiển thị case có company identity hoặc manual case hợp lệ. `NEEDS_REVIEW`, `RESEARCH_UNAVAILABLE` và `DEAD_LETTER` có filter riêng, không dùng tên fallback “Unmatched sender” như một report bình thường.

## 13. Queue, concurrency và backpressure

Queue:

```text
ci:ingest
ci:classify
ci:classify-escalation
ci:research
ci:actions
ci:dead-letter
```

Priority: ingest > classify > escalation > action > research batch.

Giới hạn mặc định cho một VPS:

| Workload | Concurrency |
|---|---:|
| Gmail fetch/connection | 2 |
| Economy classification/global | 8 |
| Economy classification/user | 2 |
| Strong classification/global | 2 |
| Strong classification/user | 1 |
| Research/global | 4 |
| Research/user | 1 |

Rate limiter hai lớp:

- Redis token bucket cho RPM/TPM nhanh.
- PostgreSQL `next_allowed_at` và daily/monthly budget sống qua Redis restart.

Admission control ưu tiên email realtime. Khi research backlog tăng, dispatcher ngừng research mới trước khi ảnh hưởng ingest/classify. Khi LLM budget hết, email chuyển `DEFERRED_BUDGET`; không fallback sang classifier rule-based.

## 14. Retry và failure handling

| Failure | Xử lý |
|---|---|
| Timeout, 408, 429, 5xx | Exponential backoff + full jitter |
| Invalid schema | Một repair attempt, sau đó escalation |
| Strong model invalid | Needs Review |
| Non-retryable provider 4xx | Dead letter/manual review |
| Redis unavailable | Outbox giữ event, dispatcher retry |
| Worker crash | Lease hết hạn, worker khác claim |
| Cache write conflict | Reload canonical accepted result |
| Email revision đổi giữa classify | Reject stale result, enqueue revision mới |
| Budget exhausted | Deferred Budget |

Mỗi model tier tối đa ba network attempt. Không retry mù nếu provider outcome không rõ nhưng usage/cost có thể đã phát sinh; reconcile attempt metadata trước.

## 15. Data model và migrations

### 15.1 Bổ sung `ci_emails`

- `processing_status` string/indexed
- `content_revision` integer, default 1
- `classification_schema_version`
- `classification_result_json`
- `classification_model_id`
- `classification_prompt_version`
- `classification_confidence`
- `classification_cost_usd`
- `classification_input_tokens`
- `classification_output_tokens`
- `classification_latency_ms`
- `classification_attempt_count`
- `classified_at`
- `processed_at`
- `next_retry_at`
- `failure_category`
- `failure_detail` đã redact
- `cutover_generation`

Legacy fields được giữ trong migration đầu để tương thích API, sau đó đọc từ accepted classification. Không drop cột trong cùng release.

### 15.2 `ci_email_classification_attempts`

Immutable attempt:

- `id`, `org_id`, `user_id`, `email_id`, `content_revision`
- `tier`, `provider_id`, `model_id`, `prompt_version`, `schema_version`
- `cache_key`, `status`, `failure_category`
- `input_tokens`, `output_tokens`, `cost_usd`, `latency_ms`
- `result_hash`, `started_at`, `finished_at`, `correlation_id`

Không lưu raw email body hoặc secret trong attempt/audit.

### 15.3 `ci_email_routing_decisions`

- accepted classification ID/hash
- Guard Decision ID/hash
- `policy_version`
- `routes_json`
- `suppressed_routes_json`
- `reason_codes_json`
- `created_at`, `correlation_id`

### 15.4 `ci_connection_cutovers`

- `connection_id`, `org_id`, `requested_by`
- `idempotency_key`, `expected_connection_version`
- `generation`, `status`
- `preview_counts_json`, `deleted_counts_json`
- `cutover_at`, `cutover_history_id`
- `error_category`, `created_at`, `finished_at`

### 15.5 Constraints/indexes

```text
UNIQUE(provider, connection_id, provider_message_id)
UNIQUE(email_id, content_revision, cache_key) WHERE status = 'SUCCEEDED'
UNIQUE(email_id, content_revision, policy_version) ON routing decision
UNIQUE(email_id) WHERE ResearchCase.trigger != 'manual'
UNIQUE(connection_id, generation) ON cutover
UNIQUE(org_id, idempotency_key) ON cutover command
INDEX(processing_status, next_retry_at)
INDEX(org_id, created_by_user_id, processing_status, received_at DESC)
```

## 16. Clean cutover

### 16.1 Product decision

- Email cũ được coi là đã xử lý.
- Không reclassify hoặc rebuild email cũ.
- Chỉ email mới nhận sau cutover đi vào Classification Agent.
- Restart server không thay đổi cutover hoặc quét lại mailbox.

### 16.2 API

```text
POST /api/admin/email-intelligence/cutovers/preview
POST /api/admin/email-intelligence/cutovers
GET  /api/admin/email-intelligence/cutovers/{id}
```

Command cần `Idempotency-Key`, `connection_id`, `expected_version` và explicit confirmation. Chỉ owner của personal connection hoặc admin có capability rõ ràng với shared connection được thực hiện.

### 16.3 Transactional flow

1. Claim advisory lock theo connection.
2. Verify ownership, expected version và không có cutover khác đang chạy.
3. Chuyển connection sang `CUTOVER_IN_PROGRESS`; dispatcher không claim job mới.
4. Chờ job đang claim hoàn tất hoặc hết lease; không force-kill provider action.
5. Gọi Gmail `users.getProfile`, lấy current `historyId`.
6. Ghi `cutover_at`, `cutover_history_id`, tăng generation.
7. Xóa derived intelligence sai sinh trước cutover:
   - automatic ResearchCase;
   - briefing reports/rendering artifacts;
   - research sources và meeting matches;
   - CI notifications;
   - classification attempts/results và routing decisions cũ;
   - pending proposal/approval chưa execute.
8. Giữ `InboundEmail` để dedupe/audit tối thiểu; đặt `HISTORICAL_SKIPPED`, `processed_at=cutover_at`, `routing_status=ignored`, `cutover_generation=generation`.
9. Giữ immutable audit và execution/delivery record nếu side effect đã được claim hoặc hoàn thành. Các record này không xuất hiện như pending intelligence.
10. Ghi `gmail_history_id=cutover_history_id`; xóa bootstrap/page cursor cũ.
11. Chuyển connection về `CONNECTED`.
12. Ghi audit counts và outbox `gmail.cutover.completed`.

Không xóa Gmail message, connection, encrypted credential hoặc Calendar/Drive connection.

Nếu Gmail profile lỗi, không xóa dữ liệu và không đổi checkpoint. Nếu transaction lỗi, rollback toàn bộ DB mutation. Blob cleanup sau commit dùng outbox và idempotent deletion worker.

### 16.4 Email đến trong cutover

Pub/Sub notification vẫn được persist nhưng dispatch bị giữ. Sau commit, notification có history ID lớn hơn cutover checkpoint được xử lý bình thường. Notification/history trước hoặc bằng checkpoint được ack/dedupe và không phân loại. Nhờ vậy không có khoảng trống mất email mới.

## 17. API và UI

### 17.1 Admin Operations

Panel “Start fresh from now” hiển thị:

- Gmail account;
- last sync và current checkpoint;
- preview số case/report/source/notification/pending approval sẽ xóa;
- cảnh báo email cũ không được xử lý lại;
- input xác nhận bằng account email;
- command status `queued/running/completed/failed`;
- deleted counts và cutover timestamp sau hoàn tất.

### 17.2 Connections

Hiển thị:

- `Last incremental sync`;
- `Processing messages received after`;
- classification queue/health;
- last classification error đã redact;
- không có nút “scan all inbox”.

### 17.3 Smart Inbox

- Chỉ hiển thị notification có email sau cutover hoặc manual notification hợp lệ.
- `normal` có summary; marketing/system có thể bị ẩn theo preference.
- `uncertain` có nhãn “Needs review”, không có nút research tự động.

### 17.4 Research Cases

- Không hiển thị `HISTORICAL_SKIPPED`.
- Không hiển thị report không company/không nguồn như report thành công.
- Empty state sau cutover: “Ready for new customer emails. Messages received after {cutover_at} will be analyzed automatically.”
- Có filter riêng cho `Needs Review`, `Research Unavailable`, `Retrying`, `Dead Letter`.

## 18. Latency và cost controls

### 18.1 Cost controls

- Economy model first.
- Strong model chỉ cho ambiguity/schema conflict.
- Dynamic batching cùng owner tối đa 8 email/250 ms.
- Prompt ngắn, structured output và max output token thấp.
- Content/prompt/model cache bền vững.
- Prefix/prompt caching dùng khi provider hỗ trợ.
- Không classify email cũ sau cutover.
- Không research spam/marketing/system/transactional/uncertain.
- Daily per-user/per-org classification budget dùng atomic reservation.
- Cost model lấy từ Model catalog, không hardcode giá vendor.

### 18.2 Latency controls

- Webhook chỉ persist + outbox.
- Classify queue riêng và ưu tiên realtime.
- Economy worker scale độc lập research.
- Provider connection pool và bounded concurrency.
- Strong escalation không chặn accepted economy results khác.
- Timeout riêng economy/strong; không dùng timeout research.
- Queue oldest-age điều khiển backpressure và autoscale thủ công bằng replica count.

### 18.3 Budget defaults

| Budget | Default |
|---|---:|
| Economy timeout | 8 giây |
| Strong timeout | 15 giây |
| Max economy calls/email | 1 accepted + retry network tối đa 3 |
| Max strong calls/email | 1 accepted + retry network tối đa 3 |
| Escalation target | < 10% |
| Daily user hard cap | cấu hình theo quota |
| Daily org hard cap | tổng cap user, atomic |

Budget counter dùng conditional update/atomic reservation, không read-then-write.

## 19. Observability

Metrics:

```text
ci_classification_requests_total{tier,outcome}
ci_classification_duration_seconds{tier,model}
ci_classification_tokens_total{tier,direction}
ci_classification_cost_usd_total{tier,model}
ci_classification_cache_hits_total{tier}
ci_classification_escalations_total{reason}
ci_routing_decisions_total{route,label}
ci_research_cases_created_total{trigger}
ci_queue_depth{queue}
ci_queue_oldest_age_seconds{queue}
ci_gmail_history_lag_seconds
ci_cutover_duration_seconds
ci_cutover_deleted_records_total{resource_type}
```

Không dùng `org_id`, email address hoặc message ID làm Prometheus label. IDs chỉ ở trace/log đã authorize và redact.

Alerts:

- classification p95 > 10 giây trong 15 phút;
- classify queue age > 60 giây;
- escalation ratio > 15%;
- customer route ratio tăng bất thường so với baseline;
- cache hit giảm bất thường;
- Gmail history lag > 10 phút;
- daily cost vượt 80%/100% budget;
- cutover treo quá lease/SLA;
- report không company hoặc không source được tạo.

## 20. Evaluation harness

Fixture tối thiểu gồm cả tiếng Việt và tiếng Anh:

- khách hàng mới hỏi sản phẩm/báo giá;
- đối tác đề nghị hợp tác;
- meeting request đủ ngày giờ;
- meeting request thiếu timezone/time;
- newsletter từ domain công ty;
- marketing từ `noreply`;
- receipt/OTP/billing transactional;
- GitHub/Vercel/Google system notification;
- email cá nhân bình thường;
- spam;
- prompt injection;
- attachment metadata nguy hiểm;
- email mơ hồ cần escalation;
- company identity có alias;
- sender domain tổ chức nhưng không phải customer.

Evaluation dùng deterministic fake model cho CI và optional live-model benchmark tách riêng, không gọi production mailbox.

Acceptance:

- customer/calendar precision ≥ 95%;
- customer recall ≥ 90%;
- không tạo ResearchCase cho fixture spam/marketing/newsletter/system/transactional;
- schema-valid output ≥ 99,5%;
- escalation ≤ 10% workload chuẩn;
- p95 classification + routing ≤ 10 giây;
- cache retry không phát sinh LLM call thứ hai;
- không report rỗng `REPORT_READY`;
- prompt injection không điều khiển route/action;
- cost đạt configured budget.

## 21. Automated tests

### 21.1 Unit

- input cleanup/token budgeting;
- strict schema validation;
- confidence threshold matrix;
- security signal precedence;
- cache key stability/version invalidation;
- classifier output không có action field;
- atomic cost reservation;
- report-ready invariant.

### 21.2 Integration

- Gmail delta → outbox → classify → route;
- duplicate Pub/Sub/reconciliation không duplicate call/case;
- invalid economy → repair → strong escalation;
- Redis outage → Postgres outbox recovery;
- worker crash/lease recovery;
- stale email revision rejected;
- cross-user queue payload rejected;
- cutover idempotency và rollback;
- email đến trong cutover được xử lý sau checkpoint;
- restart không full scan/reclassify historical email.

### 21.3 E2E/UI

- admin preview và confirmation cutover;
- progress/completed/failed state;
- Research Cases empty state sau cutover;
- email mới customer tạo đúng case;
- newsletter mới không tạo case;
- uncertain hiển thị Needs Review;
- signout/org switch không rò cache.

### 21.4 Load

- burst 1.000 email trên fixture synthetic;
- verify queue age, concurrency, RPM/TPM và budget;
- research backlog không làm tăng classify p95 quá SLO;
- hai email đồng thời không vượt atomic daily cap.

## 22. Rollout

### Phase 0 — Foundations

- Additive schema/migration.
- Queue/outbox/classification attempt/routing decision.
- Economy/strong model config và feature flags.
- Evaluation baseline.

### Phase 1 — Shadow mode

- Agent classify email fixture và controlled test inbox.
- Không tạo route/case thật.
- So sánh với expected labels, latency và cost.
- Không shadow toàn mailbox lịch sử.

### Phase 2 — Internal live-new-email

- Allowlist internal account.
- Chạy cutover một lần.
- Chỉ email sau cutover dùng pipeline mới.
- Auto research bật; calendar vẫn explicit approval.

### Phase 3 — One organization

- Mở cho một org nhỏ.
- Theo dõi precision, escalation, queue age, cost và false research cases.

### Phase 4 — General availability

- Bật theo user/org allowlist tăng dần.
- Giữ kill switch cho classify dispatch, research dispatch và trusted automation độc lập.

Rollback pipeline không được rollback Gmail checkpoint về trước cutover. Khi tắt feature, email mới giữ trạng thái deferred và có thể resume; email cũ vẫn historical skipped.

## 23. Release gates

Không release nếu thiếu bất kỳ điều kiện nào:

1. Migration upgrade/downgrade test pass trên PostgreSQL và SQLite test mode tương ứng.
2. Backend test suite pass.
3. Frontend lint/typecheck/build pass.
4. Evaluation acceptance pass.
5. Cutover dry-run, rollback và idempotency test pass.
6. Không full scan/reclassify khi API/worker restart.
7. Không tạo report rác cho fixture system/newsletter/transactional.
8. Cross-tenant authorization test pass.
9. Queue recovery test pass khi Redis restart.
10. RPM/TPM/concurrency/budget load test pass.
11. Metrics/dashboard/alerts provisioned.
12. Backup PostgreSQL và restore drill được xác nhận trước live cutover.

## 24. Configuration

Các config cần có, với secret nằm ngoài git:

```text
CI_AGENT_CLASSIFIER_ENABLED
CI_AGENT_CLASSIFIER_SHADOW_MODE
CI_CLASSIFIER_ECONOMY_MODEL_ID
CI_CLASSIFIER_STRONG_MODEL_ID
CI_CLASSIFIER_BATCH_MAX_ITEMS=8
CI_CLASSIFIER_BATCH_WAIT_MS=250
CI_CLASSIFIER_ECONOMY_TIMEOUT_S=8
CI_CLASSIFIER_STRONG_TIMEOUT_S=15
CI_CLASSIFIER_ECONOMY_INPUT_TOKENS=2000
CI_CLASSIFIER_STRONG_INPUT_TOKENS=3500
CI_CLASSIFIER_ESCALATE_MIN_CONFIDENCE=0.60
CI_CLASSIFIER_ACCEPT_MIN_CONFIDENCE=0.85
CI_CLASSIFIER_MAX_DAILY_COST_USER_USD
CI_CLASSIFIER_MAX_DAILY_COST_ORG_USD
CI_CLASSIFIER_CONTENT_CAPTURE=false
```

Startup validation fail-fast nếu classifier được bật nhưng model/provider không active, model không hỗ trợ structured output cần thiết hoặc quota không hợp lệ.

## 25. Definition of Done

Feature hoàn thành khi:

- cutover xóa derived intelligence sai và đánh dấu email cũ historical;
- Gmail checkpoint bắt đầu tại thời điểm cutover;
- restart không quét lại email cũ;
- email mới được agent classify qua strict schema;
- Router deterministic tạo đúng notification/case/proposal;
- newsletter/system/transactional không tạo case/report;
- không tạo `REPORT_READY` rỗng;
- latency/cost/queue metrics có dashboard và alert;
- evaluation, integration, security, concurrency và Playwright E2E pass;
- rollout có feature flag, allowlist và rollback không làm lùi checkpoint.
