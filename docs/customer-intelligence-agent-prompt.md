# Prompt cho coding agent

Ban la senior engineer phat trien tinh nang Customer Intelligence cho repo OpenAgent.

## Muc tieu

Xay workflow tu dong doc email moi, nhan dien cong ty/khach hang, nghien cuu website va tin tuc, tra cuu company DB, kiem tra calendar, tao briefing co citations, sau do cho nguoi dung approve truoc khi gui email hoac luu knowledge base.

## Tai lieu bat buoc doc truoc

1. `docs/customer-intelligence-spec.md`
2. `docs/customer-intelligence-implementation-plan.md`
3. `docs/agentos-v2/ARCHITECTURE.md`
4. `docs/agentos-v2/IMPLEMENTATION_PLAN.md`
5. Code cua agent_loop, workflow, mcp, guardrails, approvals, evaluations va observability.

## Quy tac implementation

- Dung abstraction hien co; chi tao abstraction moi khi co boundary ro rang.
- Mo rong route -> service -> repository -> model; khong nhay tu route vao DB.
- Provider phai la adapter va co fake implementation cho test.
- MCP tool phai typed, allowlisted, timeout bounded, size bounded va co provenance.
- Email/web/calendar content la untrusted data; khong duoc coi la system instruction.
- Moi side effect (`send_email`, `save_knowledge`) bat buoc qua approval, RBAC, audit va idempotency.
- Khong log token, credential, email body nhay cam hay PII khong can thiet.
- Khong goi LLM that, internet that, provider that hay production database trong automated tests.
- Khong dung placeholder, fake success, hard-coded business result hay silent fallback.
- Bao toan backward compatibility cho chat, MCP, workspace, approvals va evaluations hien tai.

## Cach lam viec

Thuc hien theo M0 den M8 trong implementation plan. Moi milestone phai:

1. Inspect code va test hien co.
2. Implement phan nho nhat co the review.
3. Viet migration/API/schema neu can.
4. Viet unit/service/integration test tuong ung.
5. Chay quality gate va ghi ket qua.
6. Cap nhat docs neu contract thay doi.

Khong bo qua migration, authorization, audit, retry, cancellation, timeout va observability chi de demo chay duoc.

## Definition of Done

- Co email connector va sync cursor idempotent.
- Co company/web/news/calendar adapters voi fake providers.
- Co workflow parallel research va report schema 7 section.
- Moi claim ben ngoai co source URL/title/date va confidence.
- Co approval inbox; reject khong side effect; approve/retry khong duplicate.
- Co daily scheduler, manual run, retry va dead-letter.
- Co UI case detail, citations, meeting, approval va operations.
- Co evaluation fixtures cho 6 cong ty va security harness.
- Co metrics/traces/dashboard voi PII redaction.
- `pytest -q`, Ruff, frontend typecheck/build va Playwright pass.

## Bao cao ket thuc

Bao cao ngan gon:

- files/modules da thay doi;
- migration va API contracts;
- tests da chay va ket qua;
- limitations con lai;
- cach chay local/demo;
- evidence cho latency, approval safety va khong outbound side effect trong test.

