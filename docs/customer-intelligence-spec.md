# Customer Intelligence Agent System Specification

## 1. Muc tieu

He thong tu dong theo doi email moi moi sang, phat hien email tu khach hang/doi tac, nghien cuu cong ty, kiem tra lich hop va tao briefing ngan gon de nguoi dung duyet truoc khi gui email hoac luu vao knowledge base.

He thong phai giam thao tac thu cong, nhung khong duoc tu dong gui thong tin ra ben ngoai hay ghi du lieu quan trong vao tri nho neu chua co phe duyet cua con nguoi.

## 2. Pham vi

### Trong pham vi

- Gmail va Outlook thong qua OAuth2.
- Polling va webhook/delta sync cho email, co checkpoint va idempotency.
- Trich xuat nguoi gui, cong ty, domain, noi dung, muc dich va dau hieu lich hop.
- Tra cuu website, tin tuc gan day va thong tin cong ty noi bo.
- Doi chieu voi calendar theo cong ty, domain, email va ten nguoi lien he.
- Tao report Markdown, HTML, PDF va Word; tao email draft.
- Human approval truoc khi send email va truoc khi luu knowledge base.
- Audit log, metrics, tracing, retry, dead-letter va dashboard AgentOps.
- Chay demo qua Docker Compose va tuy chon Cloudflare Tunnel/VPS.

### Ngoai pham vi giai doan dau

- Tu dong gui email khong qua approval.
- Thu thap du lieu sau login, vuot CAPTCHA, hoac scrape trai phep.
- Suy doan thong tin nhay cam ve ca nhan.
- Thay the CRM/ERP hien tai.
- Bao dam tinh day du tuyet doi cua thong tin internet.

## 3. Doi tuong va vai tro

- **User**: ket noi tai khoan, cau hinh lich chay, review va approve.
- **Email Agent**: doc email moi, trich xuat va tao draft.
- **Web Research Agent**: tim kiem, lay nguon va trich dan co ngay cap nhat.
- **Company Info Agent**: tim cong ty trong DB noi bo qua MCP.
- **Calendar Agent**: tim cuoc hop sap toi va thong tin lien quan.
- **Report Agent**: hop nhat ket qua thanh briefing co provenance.
- **Memory Agent**: luu context da duyet, lich su nghien cuu va preference.
- **Approval Agent**: tao approval request va ngan side effect khi chua duyet.
- **Orchestrator**: dieu phoi workflow, timeout, retry va state transition.

## 4. Luong nghiep vu chuan

```text
Email trigger
  -> ingest + deduplicate
  -> extract sender/company/intent
  -> parallel: web research | company DB | calendar | memory
  -> source validation + confidence scoring
  -> report generation
  -> policy/security/evaluation checks
  -> human approval
  -> send email draft and/or save knowledge document
  -> audit, metrics and memory update
```

Neu mot nhanh research loi, report van phai ghi ro phan nao khong co du lieu. Khong duoc dien thong tin phong doan vao ket qua nhu su that.

## 5. Yeu cau chuc nang

### FR-001 Ket noi email

- Ho tro OAuth2, token encryption, refresh token va revoke.
- Gmail dung historyId/page token; Outlook dung deltaLink neu provider ho tro.
- Luu `provider_message_id`, `thread_id`, `received_at`, `sync_cursor`.
- Cung mot email chi duoc tao mot `ResearchCase`, ke ca khi worker retry.
- Khong log access token, refresh token, body nhay cam hoac attachment binary.

### FR-002 Phan tich email

Trich xuat sender name/email, recipients, subject, body text, attachment metadata, company name, email domain, website candidate, contact name/title, intent, meeting hints, confidence va evidence span. Email co prompt injection phai duoc danh dau; noi dung email chi la untrusted data, khong phai system instruction.

### FR-003 Web research

- Tim website chinh thuc, trang san pham, about/company profile va tin tuc.
- Moi claim phai co URL, title, publisher, published date, retrieved date va trich dan ngan.
- Tin tuc mac dinh trong 30 ngay; cho phep cau hinh 7/30/90 ngay.
- Loai bo duplicate, redirect nguy hiem, domain khong tin cay va ket qua khong co provenance.
- Neu khong co search provider, workflow phai tra ve `research_unavailable`, khong fake ket qua.

### FR-004 Company database

MCP contract toi thieu:

```json
{"name":"company_search","input":{"query":"FPT Software","limit":5}}
{"name":"company_get","input":{"company_id":"company-123"}}
```

Ket qua can co `company_id`, ten chuan hoa, aliases, industry, products, contacts, source va `updated_at`.

### FR-005 Calendar

MCP contract toi thieu:

```json
{"name":"calendar_list_events","input":{"from":"2026-08-06T00:00:00Z","to":"2026-08-13T00:00:00Z"}}
```

Match event theo email domain, attendee email, company alias va ten cong ty. Report phai phan biet `confirmed_match` va `possible_match`.

### FR-006 Report

Report co schema on dinh:

1. Executive summary.
2. Company overview, industry, products/services.
3. Recent news va source links.
4. Contact information.
5. Upcoming meetings, attendees, agenda va preparation notes.
6. Open questions, missing data, confidence.
7. Sources va timestamps.

Report khong duoc hien thi claim khong co source neu claim do la thong tin ben ngoai. Ho tro Markdown lam canonical format; HTML/PDF/DOCX la renderer.

### FR-007 Approval va side effects

- Tao approval cho `send_email`, `save_knowledge`, va policy risk cao.
- Approval request co case id, diff/payload, target, expires_at, requester, reviewer, decision va audit trail.
- Reject/expire khong duoc thuc hien side effect.
- Approve phai idempotent; cung mot approval khong duoc gui hai lan.
- Email chi duoc tao draft truoc approval; send sau approval moi duoc goi provider.

### FR-008 Lich chay va xu ly loi

- Cho phep schedule moi sang theo timezone cua user.
- Co manual run cho mot email/case.
- Retry exponential backoff co jitter cho loi tam thoi; khong retry loi auth/validation.
- Case loi sau retry vao dead-letter, co nut retry thu cong.
- Worker restart khong lam mat state va khong tao duplicate side effect.

### FR-009 UI

Can bo sung hoac mo rong cac view hien co:

- Integrations: email, calendar, research provider, company DB.
- Cases: danh sach case theo status, source, confidence, deadline.
- Case detail: timeline agent/tool, report, citations, meeting, approval actions.
- Approval inbox: diff truoc/sau, recipient, attachment, risk va approve/reject.
- Schedules: timezone, gio chay, mailbox/folder va policy.
- Operations: retry, dead-letter, latency, token/cost, tool failure.

Khong duoc dua secrets vao client. Action nhay cam can server-side authorization va audit.

## 6. Domain model va state machine

Entities toi thieu:

- `EmailConnection`: provider, account, encrypted credentials, cursor, status.
- `InboundEmail`: provider ids, headers, normalized body, attachments, received time.
- `ResearchCase`: email id, company, status, workflow run id, error, timestamps.
- `ResearchSource`: case id, url, source type, title, dates, excerpt, trust, hash.
- `Meeting`: provider event id, time, attendees, match type, confidence.
- `BriefingReport`: case id, canonical markdown, rendered artifacts, version, confidence.
- `ApprovalRequest`: action, payload hash, status, reviewer, expiration, audit id.
- `DeliveryAttempt`: provider, draft/send id, status, error, idempotency key.

Case states:

```text
NEW -> INGESTED -> RESEARCHING -> REPORT_READY -> AWAITING_APPROVAL
AWAITING_APPROVAL -> APPROVED -> EXECUTING -> COMPLETED
AWAITING_APPROVAL -> REJECTED | EXPIRED
RESEARCHING/EXECUTING -> RETRYING -> RESEARCHING/EXECUTING
RETRYING -> DEAD_LETTER
```

## 7. Agent va tool contract

Agent phai tra ve typed result, khong tra text tu do lam contract. Moi result co `status`, `data`, `sources`, `warnings`, `confidence`, `trace_id`.

Tool groups:

- Email: `email_list_new`, `email_get`, `email_create_draft`, `email_send`, `email_delivery_status`.
- Research: `web_search`, `web_fetch`, `news_search`.
- Company: `company_search`, `company_get`.
- Calendar: `calendar_list_events`, `calendar_get_event`.
- Knowledge: `knowledge_search`, `knowledge_upsert`.
- Existing Drive/artifact tools: reuse MCP client va workspace artifact pipeline.

Tool names va input phai duoc allowlist theo agent. Tool result phai duoc gioi han kich thuoc, timeout va domain. Khong cho phep agent tu tao URL callback hoac recipient ngoai policy.

## 8. Bao mat va an toan

- Tenant/user isolation o moi query va moi MCP credential.
- Encrypt secrets at rest; redact logs; khong gui email neu recipient chua duoc xac nhan.
- Prompt injection defense: tach instructions va external content, scan output, block secret exfiltration va external send.
- SSRF defense cho web fetch: allowlist scheme, block private IP/metadata endpoint, redirect revalidation.
- Attachment defense: size/type limit, malware scan hook, khong execute file email.
- Approval payload phai hash va hien thi recipient, links, attachments, thay doi.
- Rate limit, budget limit, per-run timeout va cancellation.

## 9. Non-functional requirements

- Daily run p95 <= 42 giay trong evaluation fixture khi provider response da cache.
- UI hien thi trang thai ban dau trong <= 1 giay sau trigger; progress phai streaming/polling theo run state.
- Research co toi thieu 12 sources trong fixture co du lieu; tin tuc gan nhat 30 ngay.
- Retry-safe va restart-safe; khong duplicate email send.
- Metrics: request success/failure, tool success/failure, latency, queue age, tokens, cost, retries, approval age.
- Tracing co `run_id`, `case_id`, `agent`, `tool`, `provider`, `tenant_id` da redact.

## 10. Evaluation va acceptance

Fixture bat buoc: FPT Software, Vinamilk, Samsung Vietnam, Shopee Vietnam, Viettel Solutions, Bosch.

Moi fixture kiem tra dung company identity va company DB match; du 12 sources co URL/title/date va khong duplicate; news trong 30 ngay; meeting match dung; report co du 7 section; khong hallucinate khi provider thieu du lieu; latency <= 42 giay; prompt injection khong lay duoc secret va khong send email; approval reject khong tao side effect; approval retry khong duplicate side effect.

Definition of Done chi dat khi co unit, integration, security, evaluation va manual approval-flow test. Test tu dong khong duoc goi LLM that, database production hay provider that.

## 11. Mapping voi code hien tai

Tiep tuc dung cac module hien co:

- `backend/app/core/agent_loop.py`: agent execution va streaming state.
- `backend/app/core/workflow/engine.py`: DAG/orchestration.
- `backend/app/mcp/client.py`: MCP tool transport.
- `backend/app/core/guardrails/`: approval, budget, injection, secret redaction.
- `backend/app/services/evaluation_service.py` va `backend/app/evals/`: evaluation harness.
- `backend/app/core/observability/` va `observability/grafana/`: tracing/metrics/dashboard.
- `frontend/app/approvals/`, `frontend/app/evaluations/`, `frontend/app/mcp/`: UI patterns.

Khong tao integration framework moi neu abstraction hien tai co the mo rong qua provider adapter va MCP server.

