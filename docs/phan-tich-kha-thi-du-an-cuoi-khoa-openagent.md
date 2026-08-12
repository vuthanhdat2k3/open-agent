# Phân tích khả thi: triển khai đề án cuối khóa trên OpenAgent

> Phạm vi: đánh giá khả năng triển khai đề án trong `C:\Users\PC\Downloads\Du-an-cuoi-khoa.pptx` trên codebase OpenAgent hiện tại.
>
> Ngày đánh giá: 2026-08-11  
> Kết luận ngắn: **khả thi cao cho MVP/demo; cần bổ sung trước khi production pilot; chưa đủ bằng chứng để cam kết production đầy đủ.**

## 1. Kết luận điều hành

Đề án có thể triển khai trên OpenAgent mà không cần xây một agent platform mới. OpenAgent đã có phần lớn nền tảng cần thiết:

- FastAPI backend và Next.js frontend;
- agent loop, tool calls, streaming và delegation;
- graph workflow engine;
- MCP client/server integration;
- Gmail/Calendar/Drive Customer Intelligence connector;
- web search và web fetch;
- RAG service;
- approval workflow;
- prompt-injection guardrail và secret redaction;
- audit log, quota và observability;
- evaluation suite và quality gate;
- Docker Compose, Redis/arq worker, PostgreSQL, MinIO, Qdrant, SearXNG, Crawl4AI và Grafana.

Phần còn thiếu chủ yếu nằm ở product completion và acceptance evidence:

- scheduler chưa tự nối từ email sync sang research;
- CI report mới có Markdown, chưa có PDF/DOCX thực tế;
- `save_knowledge` chưa có backing sink trong delivery flow;
- frontend chưa có workspace riêng cho cases/schedules/operations;
- retry/dead-letter cho CI chưa hoàn chỉnh;
- chưa có evaluation fixture chứng minh 6 công ty, 12 nguồn, 98% và 42 giây;
- company database phụ thuộc external API/configuration.

## 2. Mức độ khả thi theo cấp độ

| Mức triển khai | Đánh giá | Điều kiện |
|---|---|---|
| MVP/demo cuối khóa | **Khả thi cao** | Markdown, fake/sandbox provider, approval và email sandbox |
| Production pilot | **Khả thi sau khi bổ sung** | Nối scheduler→research, UI case, retry, RAG sink, provider config |
| Production đầy đủ theo đề án | **Chưa sẵn sàng** | Cần PDF/DOCX, evaluation, security hardening, operations và SLA evidence |
| Production multi-tenant quy mô lớn | **Chưa nên cam kết** | Cần rà soát ownership, distributed scheduler lease, quota/provider reliability và retention |

## 3. Bảng đối chiếu yêu cầu và thành phần hiện có

| Yêu cầu đề án | Trạng thái | Thành phần/bằng chứng |
|---|---|---|
| Đọc email mới | Đã có một phần | `customer_intelligence/ingest.py`, Gmail MCP |
| Chạy mỗi sáng | Có scheduler nhưng flow chưa đầy đủ | `scheduler.py`, arq cron trong `app/worker.py` |
| Gmail OAuth2 | Đã có | `oauth.py`, encrypted credentials, refresh/revoke |
| Email Agent | Đã có | `providers/email.py`, CI tools |
| Web Research Agent | Đã có | SearXNG/DDG trong `customer-intelligence-mcp` |
| Tin tức 7/30/90 ngày | Có contract | `NEWS_SEARCH_SCHEMA`, `lookback_days` |
| Company Info Agent | Có adapter | `McpCompanyProvider`, external company API |
| Calendar Agent | Đã có | Google Calendar MCP, `match_meetings()` |
| Meeting match | Đã có | `confirmed_match`, `possible_match`, confidence |
| Report 7 section | Đã có Markdown | `workflow.py`, `renderer.py` |
| PDF/Word | Chưa có thực tế | `BriefingReport.rendering` hiện vẫn `None` |
| Memory | Có nền tảng chung | session/tiered memory và RAG |
| Save Knowledge Base | Chưa hoàn chỉnh | `save_knowledge` bị reject do chưa có sink |
| Human approval | Đã có | `ApprovalRequest`, approval routes, expiry và audit |
| Gửi email sau approval | Đã có | `delivery.py`, Gmail draft/send |
| Idempotency delivery | Đã có | `DeliveryAttempt`, idempotency key |
| Prompt injection | Có baseline | `scan_for_prompt_injection()`, guardrails |
| Secret redaction | Đã có | OAuth/log redaction và observability redaction |
| Evaluation framework | Đã có framework chung | evaluation suites/runs/graders |
| Evaluation riêng cho 6 công ty | Chưa chứng minh | Chưa thấy fixture acceptance tương ứng |
| AgentOps | Đã có baseline | Prometheus, Grafana, tracing, Langfuse tùy cấu hình |
| CI-specific frontend | Chưa đầy đủ | Có integrations/approvals generic, chưa có case workspace |

## 4. Luồng hiện tại trong backend

Luồng backend Customer Intelligence hiện có thể mô tả như sau:

```text
Gmail OAuth
  → MCP email provider
  → sync cursor + pagination
  → deduplicate provider_message_id
  → lưu InboundEmail
  → tạo ResearchCase
  → company matching
  → web/news research
  → calendar matching
  → lưu ResearchSource/Meeting
  → tạo BriefingReport Markdown
  → REPORT_READY
  → tạo approval
  → approve
  → tạo draft và send email
```

Các API chính đã tồn tại:

```text
GET  /api/customer-intelligence/connections
POST /api/customer-intelligence/connections/{id}/sync

GET  /api/customer-intelligence/schedules
POST /api/customer-intelligence/schedules
POST /api/customer-intelligence/schedules/{id}/run

GET  /api/customer-intelligence/cases
GET  /api/customer-intelligence/cases/{id}
POST /api/customer-intelligence/cases/{id}/research

POST /api/customer-intelligence/cases/{id}/deliver
POST /api/customer-intelligence/cases/{id}/approval/{approval_id}/decide
```

## 5. Các điểm đã có và đủ tốt cho MVP

### 5.1. Email ingestion và deduplication

`ingest.py` đã có:

- sync cursor;
- pagination giới hạn;
- `provider_message_id`;
- content hash;
- lưu sender/domain/subject/body/attachments metadata;
- tạo một `ResearchCase` cho email mới;
- bỏ qua email trùng khi worker retry;
- đánh dấu prompt injection trong email body.

Credential được mã hóa ở database và được load/refresh khi cần.

### 5.2. Research và provenance

`workflow.py` đã có:

- company matching;
- web search và news search;
- giới hạn timeout;
- cảnh báo khi search lỗi hoặc không có dữ liệu;
- SSRF URL safety check;
- loại duplicate URL;
- content hash;
- source title, publisher, published date, retrieved date và excerpt;
- calendar matching;
- report confidence.

Thiết kế “không fake kết quả khi provider lỗi” phù hợp với yêu cầu an toàn của đề án.

### 5.3. Approval và delivery safety

`delivery.py` đã có:

- approval theo case/action;
- payload hash;
- expiration;
- kiểm tra payload không bị thay đổi;
- reject/expire không thực hiện side effect;
- validate recipient đơn lẻ;
- tạo Gmail draft;
- gửi sau approval;
- `DeliveryAttempt` và idempotency key;
- ngăn gửi lặp khi replay.

Đây là một trong những phần đã gần đạt acceptance nhất.

### 5.4. Scheduler và observability

Scheduler đã hỗ trợ:

- run time theo timezone;
- UTC persistence;
- DST-aware calculation qua `zoneinfo`;
- manual run;
- correlation ID;
- audit event;
- metrics không chứa org/connection ID.

Worker đã đăng ký CI scheduler tick mỗi 5 phút. Grafana dashboard có panel về sync rate, cases ingested, sync duration và approval age.

## 6. Các khoảng trống cần xây thêm

### 6.1. Nối scheduler với research workflow

Hiện tại `_ci_scheduler_tick()` gọi `run_due_schedules()`, còn `run_due_schedules()` chủ yếu gọi `sync_connection()`. Kết quả là scheduler tạo case mới nhưng chưa tự động nghiên cứu và tạo briefing.

Cần bổ sung một trong các hướng:

```text
sync email
  → enqueue từng ResearchCase
  → worker chạy research
  → tạo report
  → chờ user review
```

hoặc:

```text
sync email
  → tạo durable workflow run
  → workflow ingest/research/report
  → lưu state và approval request
```

Không nên chạy research dài trực tiếp trong HTTP request.

### 6.2. Report PDF/DOCX và artifact storage

Hiện `renderer.py` chỉ có `render_markdown()`. Model có trường `rendering` dành cho HTML/PDF/DOCX nhưng chưa được populate.

Cần bổ sung:

- HTML renderer;
- PDF renderer;
- DOCX renderer;
- artifact storage trên MinIO hoặc workspace artifact pipeline;
- API download artifact;
- snapshot test cho từng định dạng;
- metadata version, content hash và case ID.

### 6.3. Knowledge Base sink

`save_knowledge` hiện được khai báo trong schema nhưng `delivery.py` chủ động trả lỗi:

```text
save_knowledge has no backing sink yet; only send_email is available
```

Cần nối action này vào RAG service sau approval:

- chuyển canonical Markdown thành tài liệu;
- thêm metadata `org_id`, `case_id`, company, source URLs, report version;
- ghi provenance;
- dùng collection đúng tenant;
- tạo DeliveryAttempt/idempotency riêng;
- không ingest nếu approval reject/expire.

### 6.4. Company database

Company provider hiện phụ thuộc `CI_COMPANY_API_URL` và `CI_COMPANY_API_KEY`. Khi không có cấu hình, MCP trả `research_unavailable` thay vì dữ liệu fixture.

Để demo cần chọn rõ một phương án:

1. fake company provider/MCP;
2. company API sandbox;
3. dữ liệu công ty nội bộ trong RAG/DB;
4. chỉ demo web research và nêu company DB là dependency.

Không nên hard-code thông tin FPT, Vinamilk hoặc công ty khác vào production code để làm giả thành công.

### 6.5. Frontend cho CI

Frontend hiện có `/integrations` và `/approvals` nhưng chưa có CI workspace đầy đủ.

Nên bổ sung:

- `Cases` list với filter status/confidence;
- `Case detail` với report, citations, meeting và timeline;
- approval card hiển thị recipient, links, attachments, risk và expiration;
- `Schedules` với timezone và manual run;
- `Operations` với retry/dead-letter;
- progress polling hoặc SSE theo case/workflow run.

### 6.6. Retry và dead-letter

State machine đã có `RETRYING` và `DEAD_LETTER`, nhưng cần hoàn thiện:

- exponential backoff + jitter;
- retry riêng cho lỗi tạm thời;
- không retry auth/validation error;
- dead-letter record;
- manual retry endpoint;
- reconcile provider delivery khi worker crash;
- UI operations;
- alert theo queue age và dead-letter count.

### 6.7. Multi-agent trace

OpenAgent có agent loop, delegation và workflow engine chung. Tuy vậy CI workflow hiện vẫn là service workflow chuyên biệt, chưa phải bảy agent độc lập có node/trace riêng.

MVP có thể mô tả đây là bảy vai trò logic trong orchestrator. Nếu đề án yêu cầu chứng minh multi-agent, nên tách các node:

```text
EmailExtraction
CompanyLookup
WebResearch
CalendarMatch
MemoryRecall
ReportGeneration
ApprovalAndDelivery
```

Mỗi node cần typed input/output, timeout, warning, confidence và trace span.

## 7. Bằng chứng kiểm thử hiện tại

Đã chạy nhóm test CI tập trung với observability và Langfuse tắt:

```text
tests/test_customer_intelligence_core.py
tests/test_scheduler.py
tests/test_schedule_api.py
tests/test_delivery.py
```

Kết quả:

```text
24 passed
190 warnings
6.29s
```

Các hành vi đã được kiểm chứng:

- async company matching;
- credential encryption dùng nonce mới;
- scheduler UTC và Asia/Bangkok;
- scheduler skip future schedule;
- manual/scheduled sync;
- dedup email;
- metrics không làm lộ PII identifiers;
- schedule CRUD;
- manual schedule run;
- audit log và correlation ID;
- approval idempotency;
- reject không tạo side effect;
- expired approval;
- approve gửi một lần;
- replay approval bị chặn;
- delivery attempt và approval age metrics.

Các kiểm tra nền tảng khác đã có trong phiên đánh giá:

- `npm run typecheck`: pass;
- `python -m ruff check app tests`: pass;
- nhóm auth/authz/guardrails/quota/workflow: `58 passed`;
- full backend test khi observability tắt: `269 passed, 8 errors`;
- 8 error liên quan môi trường thiếu package `langfuse`.

Các test trên chứng minh logic safety/core hiện có, nhưng chưa chứng minh các mục tiêu 98%, 42 giây và 12 nguồn.

## 8. Các mục tiêu chưa được chứng minh

Các giá trị sau trong PowerPoint/spec hiện nên được xem là acceptance target:

- completeness 98%;
- report latency 42 giây;
- 12 nguồn tham khảo;
- news trong 30 ngày;
- chất lượng meeting preparation.

Chưa có bằng chứng benchmark CI chính thức cho:

- sáu fixture FPT Software, Vinamilk, Samsung Vietnam, Shopee Vietnam, Viettel Solutions, Bosch;
- grader completeness/accuracy/freshness;
- p95 latency 42 giây;
- bắt buộc tối thiểu 12 source;
- không hallucinate với provider thiếu dữ liệu trên bộ fixture.

Cần xây evaluation harness riêng cho Customer Intelligence thay vì chỉ dùng evaluation framework chung.

## 9. Rủi ro và biện pháp giảm thiểu

### 9.1. Provider quota và độ ổn định

**Rủi ro:** Google, search provider hoặc company API giới hạn quota, timeout hoặc thay đổi response.

**Giảm thiểu:** cursor, pagination, cache, timeout, retry có backoff, circuit breaker, provider adapter và fake provider trong test.

### 9.2. Chất lượng web research

**Rủi ro:** nguồn trùng, cũ, thiếu ngày xuất bản hoặc không phải nguồn chính thức.

**Giảm thiểu:** provenance bắt buộc, source confidence, freshness filter, domain policy, duplicate removal và explicit missing-data warning.

### 9.3. Prompt injection và secret exfiltration

**Rủi ro:** email hoặc web page chứa chỉ dẫn giả nhằm khiến agent gửi secret hoặc gửi email trái phép.

**Giảm thiểu:** trust boundary, scan injection, tool allowlist, secret redaction, approval bắt buộc và security harness.

### 9.4. Duplicate email send

**Rủi ro:** worker crash giữa provider call và database update.

**Giảm thiểu:** DeliveryAttempt, payload hash, idempotency key, pending reconciliation và provider delivery status.

### 9.5. Multi-worker scheduler

**Rủi ro:** process-local `asyncio.Lock` không ngăn hai worker process cùng chạy một schedule.

**Giảm thiểu:** DB lease hoặc Redis distributed lock, unique execution record và atomic claim.

### 9.6. Tenant/user isolation

**Rủi ro:** organization scope đúng nhưng user thường có thể thấy hoặc sử dụng resource của user khác nếu ownership không được áp dụng ở mọi query.

**Giảm thiểu:** repository-level org/user scoping, test chéo user/organization, kiểm tra permission cho case/connection/schedule/approval và audit review.

### 9.7. Docker sandbox

**Rủi ro:** Docker socket proxy giảm blast radius nhưng bind mount host vẫn cần policy chặt.

**Giảm thiểu:** không cho phép host bind mount tùy ý, sandbox runner độc lập, network none, resource limit và review tool policy.

## 10. MVP đề xuất cho demo cuối khóa

Phạm vi MVP nên là:

```text
Gmail OAuth sandbox
  → daily/manual sync
  → detect inbound email
  → fake/internal company provider
  → web/news research fixture hoặc SearXNG
  → optional Calendar matching
  → Markdown briefing
  → human approval
  → email tới sandbox recipient
```

MVP nên cam kết rõ:

- một provider email: Gmail;
- một calendar provider: Google Calendar;
- report canonical Markdown;
- send email chỉ sau approval;
- fake provider cho automated evaluation;
- không dùng production secret;
- không gửi email tới người nhận thật trong automated test.

Có thể hoãn PDF/DOCX và Knowledge Base nếu thời gian hạn chế, nhưng phải ghi rõ đây là limitation của MVP. Nếu slide bắt buộc trình diễn Knowledge Base, cần ưu tiên làm RAG sink trước UI nâng cao.

## 11. Roadmap triển khai

### Giai đoạn 1 — Hoàn chỉnh demo MVP

1. Nối scheduled sync với research job.
2. Tạo case list/detail tối thiểu.
3. Hiển thị Markdown report và citations.
4. Hiển thị approval recipient, payload, expiration.
5. Thêm end-to-end test email → case → report → approval → email.
6. Dùng fake provider và email sandbox.
7. Chạy Docker Compose hoặc Cloudflare Tunnel.

### Giai đoạn 2 — Production pilot

1. Chuyển research/delivery sang durable queue.
2. Thêm PDF/DOCX và artifact storage.
3. Nối `save_knowledge` vào RAG/Qdrant.
4. Thêm retry/backoff/dead-letter/manual retry.
5. Thêm distributed lease cho scheduler.
6. Hoàn thiện frontend Cases/Schedules/Operations.
7. Bổ sung cross-user/cross-tenant authorization tests.

### Giai đoạn 3 — Evaluation và security hardening

1. Tạo fixture cho sáu công ty trong đề án.
2. Viết grader completeness, source, freshness, matching và hallucination.
3. Đo p95 latency, cost, token, tool failure và approval age.
4. Security test prompt injection, SSRF, secret exfiltration và unauthorized send.
5. Chỉ công bố 98%/42 giây/12 nguồn sau khi benchmark reproducible.
6. Thiết lập alert và runbook cho provider failure, dead-letter và approval backlog.

## 12. Khuyến nghị kiến trúc

Không nên tạo một integration framework mới. Nên tiếp tục dùng các abstraction hiện có:

- route → service → repository → model;
- provider adapter cho Gmail/Calendar/company/research;
- MCP cho connector stateless;
- workflow engine cho orchestration;
- approval framework cho side effects;
- RAG service cho Knowledge Base;
- observability context cho trace/metrics/redaction;
- evaluation service cho quality gate.

Mỗi side effect cần có đủ bốn lớp bảo vệ:

```text
RBAC
  + policy/allowlist
  + human approval
  + idempotent audited execution
```

## 13. Kết luận cuối

OpenAgent là nền tảng phù hợp để triển khai đề án cuối khóa. Phần lớn backend core đã tồn tại và đã có test chứng minh các hành vi quan trọng như deduplication, scheduler, approval safety và delivery idempotency.

Để demo thành công, ưu tiên theo thứ tự:

1. nối scheduler với research;
2. hoàn thiện case review UI tối thiểu;
3. chạy bằng fake/sandbox provider;
4. chứng minh approval reject/approve và không gửi trùng;
5. sau đó mới mở rộng PDF/DOCX, Knowledge Base, retry/dead-letter và evaluation sáu công ty.

**Đánh giá cuối cùng:** đề án khả thi cao ở mức MVP/demo, khả thi có điều kiện ở mức production pilot và chưa đủ bằng chứng để gọi là production-ready theo toàn bộ tiêu chí trong PowerPoint.
