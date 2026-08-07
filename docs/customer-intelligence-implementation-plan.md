# Customer Intelligence Implementation Plan

## Nguyen tac

- Mo rong pattern route -> service -> repository -> model hien co.
- Dung async worker/queue cho ingestion va workflow; API chi tao run va tra status.
- Dung Google provider adapter cho Gmail/Calendar/Drive qua MCP, khong rải logic provider vao agent.
- Dung fake provider/MCP trong test; khong goi LLM, DB production hay internet trong unit test.
- Moi milestone phai co migration, test, observability va rollback note neu co side effect.

## M0 - Baseline va contract

- Doc cac architecture/implementation docs va code agent/workflow/approval/eval/observability.
- Chot JSON schema cho domain entities, workflow events va tool results.
- Tao feature flag `customer_intelligence` va config cho provider fake.

**Exit criteria:** schema review xong, khong breaking API hien tai, test baseline xanh.

## M1 - Persistence va integration credentials

- Tao models/migrations cho connection, email, case, source, meeting, report, approval action, delivery attempt.
- Tao encrypted credential storage va token refresh interface.
- Tao repository voi tenant/user scoping, unique keys cho provider ids va idempotency keys.
- Tao API connect/disconnect/status; secret khong bao gio tra ve client.

**Tests:** migration test, repository isolation, duplicate insert, token redaction.

**Exit criteria:** co the tao connection va sync cursor ma chua can provider that.

## M2 - Email ingestion

- Implement Gmail adapters through MCP: list new, get message, cursor, draft, send, delivery status.
- Implement poller/webhook entrypoint va job deduplication.
- Normalize MIME, plain text, HTML, sender/domain va attachment metadata.
- Them prompt-injection scan cho email body va attachment names.

**Tests:** MCP Gmail connector, cursor resume, pagination, retry, auth failure, MIME parsing.

**Exit criteria:** email fixture tao dung mot case sau restart va khong send email.

## M3 - Research, company va calendar

- Implement provider interfaces cho web/news search va fetch co SSRF policy.
- Implement company DB MCP adapter va calendar MCP/provider adapter.
- Implement normalization/matching cho aliases, domain, attendees va confidence.
- Persist source provenance, evidence hash, retrieved time va warnings.

**Tests:** fake MCP servers, 12-source fixture, stale news filtering, ambiguous company, no-data path, SSRF block.

**Exit criteria:** case fixture co research/company/calendar result typed, co citations va confidence.

## M4 - Workflow va report

- Tao workflow DAG: ingest -> extract -> parallel research -> validate -> report.
- Mo rong agent loop de phan biet untrusted content voi system instructions.
- Tao canonical report schema va renderer Markdown/HTML/PDF/DOCX.
- Tao report versioning va artifact storage theo case.

**Tests:** deterministic workflow with fake model, partial branch failure, timeout, cancellation, report schema, renderer snapshot.

**Exit criteria:** report co 7 section, claim/source mapping, missing-data warnings va khong hallucinate trong fixture.

## M5 - Approval va delivery

- Tao approval request cho send email va save knowledge.
- Tao approve/reject/expire endpoints voi RBAC, audit va idempotency.
- Tao draft email co report attachment/link; send chi sau approval.
- Tao knowledge upsert chi sau approval va luu provenance.
- Tao delivery status va retry/dead-letter.

**Tests:** reject no side effect, approve once, concurrent approve, retry after timeout, wrong recipient, expired approval.

**Exit criteria:** manual flow end-to-end tu case den approval den delivery voi fake provider.

## M6 - Scheduler va operations

- Them daily schedule theo timezone, manual run, retry va dead-letter UI/API.
- Them metrics/traces: case/run/agent/tool/provider, cost, latency, queue age, approval age.
- Them Grafana panels va alerts tach khoi agent port.
- Them structured audit events va correlation id.

**Tests:** scheduler timezone, worker restart, backoff, metrics labels khong leak PII, alert smoke test.

**Exit criteria:** run p95 fixture <= 42 giay, dashboard xem duoc mot case end-to-end.

## M7 - Frontend

- Integrations page cho OAuth/provider status.
- Cases list/detail voi timeline, source citations, warnings, confidence va meeting.
- Approval inbox hien thi payload diff, recipient, attachment, risk va expiration.
- Schedule/operations view cho manual run, retry, dead-letter.
- Reuse UI state/streaming patterns hien co; khong expose credential.

**Tests:** component tests cho loading/error/empty/approval states; Playwright cho connect fake provider, case review, reject/approve va duplicate click.

**Exit criteria:** user co the theo doi case, xem report, reject va approve ma khong can devtools.

## M8 - Evaluation, security va demo

- Tao eval fixtures: FPT Software, Vinamilk, Samsung Vietnam, Shopee Vietnam, Viettel Solutions, Bosch.
- Tao scorecard completeness, accuracy, citations, freshness, meeting readiness, latency.
- Tao security harness cho prompt injection, SSRF, secret exfiltration va unauthorized send.
- Tao compose profile voi fake providers; viet runbook Cloudflare Tunnel/VPS.
- Chay full backend tests, frontend typecheck/build, integration compose va Playwright.

**Exit criteria:** all gates pass; co evidence report; demo khong dung production secret va khong send ra email that.

## Test matrix

| Lop | External services | LLM | Database | Muc tieu |
|---|---|---|---|---|
| Unit | fake | fake/deterministic | SQLite/temp | parser, policy, matching, state |
| Service | fake MCP/provider | stub model | test DB | retries, repositories, report |
| Integration | compose fake services | stub model | disposable Postgres/Redis | queue, MCP, OAuth callback |
| E2E | mock/fake only | stub model | disposable | UI workflow va approval |
| Manual demo | sandbox accounts | configured model | demo DB | OAuth, research quality, UX |

## Commands va quality gate

```powershell
pytest -q
ruff check backend
cd frontend
npm run typecheck
npm run build
```

Truoc merge phai kiem tra `git diff --check`, migration clean, no secret trong diff, va test khong tao outbound email/search that.

## Rủi ro va cach giam thieu

- **Provider rate limit:** cursor, backoff, cache, quota va dead-letter.
- **Research khong on dinh:** source confidence, timeout, partial result va explicit warning.
- **Prompt injection:** trust boundary, tool allowlist, output policy va approval.
- **Duplicate send:** idempotency key + delivery record + transactional state transition.
- **PII leak:** field-level redaction, tenant scoping, retention policy va audit review.

