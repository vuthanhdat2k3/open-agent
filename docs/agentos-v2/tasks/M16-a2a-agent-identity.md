# M16 — Liên thông A2A + Danh tính riêng cho Agent

## Branch

`agentos-v2/m16-a2a-agent-identity` từ `main` (sau khi M13 merge).

## Depends on

- **M13** — mọi lời gọi liên-agent phải trace/audit được ngay từ đầu.
- **M3** — RBAC + tool capability gate (A2A client phải đi qua gate này).

## Goal

Hai mục tiêu ghép chung vì chúng chạm cùng một bề mặt (agent gọi ra ngoài /
bên ngoài gọi vào):

1. OpenAgent **nói được A2A** — phơi agent ra ngoài và gọi agent bên ngoài.
2. Mỗi agent có **danh tính riêng** thay vì dùng chung credential của org,
   và mọi hành động truy được về chuỗi uỷ quyền.

## Bối cảnh thị trường

A2A v1.0 (4/2026), Google trao cho Linux Foundation, 150+ tổ chức, đã tích
hợp AWS/Azure/GCP. MCP giải quyết tầng *tool*, A2A giải quyết tầng *agent* —
hai chuẩn bổ sung nhau, không thay thế nhau. OpenAgent đã có MCP client,
thiếu hẳn tầng A2A.

Về danh tính: chuẩn đang hội tụ là OAuth 2.0 Token Exchange (RFC 8693) với
claim `act` để giữ chuỗi uỷ quyền. Nguyên tắc ngành: **uỷ quyền thay vì
mạo danh** — agent không được mượn nguyên credential của người dùng.

> Spec A2A còn đang tiến hoá. **Đọc lại spec chính thức tại thời điểm
> implement**, đừng code theo mô tả trong file này như thể nó là spec.

## Scope

**Trong phạm vi**: A2A server (Agent Card + task endpoint), A2A client
(gọi agent ngoài như một tool), `AgentIdentity`, token exchange nội bộ,
chuỗi uỷ quyền trong audit.

**Ngoài phạm vi**: DID/Verifiable Credentials (KYA-OS) — chưa đủ chín;
agent marketplace; thanh toán giữa agent.

## Phần 1 — A2A Server

Phơi agent hiện có ra ngoài, **không** tạo khái niệm agent mới.

- `GET /.well-known/agent-card.json` — Agent Card mô tả năng lực. Sinh từ
  `Agent` + `AgentRelease` đang active (name, description, skills suy ra từ
  `tools`, auth requirement).
  - Chỉ liệt kê agent có `a2a_exposed=True` (cột mới, **mặc định False** —
    phơi agent ra ngoài phải là hành động chủ động).
- `POST /a2a/tasks` — nhận task từ agent ngoài, map vào `agent_loop` hiện có.
- `GET /a2a/tasks/{id}` — trạng thái + kết quả.
- Streaming: dùng lại SSE đã có cho chat.

**Bắt buộc**: request A2A vào phải đi qua đúng auth + quota + guardrail như
request thường. Không có đường tắt "vì là agent nội bộ".

## Phần 2 — A2A Client

- Tool mới `call_external_agent` với `risk_tier=RiskTier.network`.
- Đăng ký agent ngoài như đăng ký MCP server hiện tại (bảng
  `external_agents`: `org_id`, `name`, `agent_card_url`, `auth_config`,
  `enabled`).
- Kết quả trả về đi qua `wrap_untrusted_if_flagged` + `scan_and_redact` —
  **output của agent ngoài là untrusted không khác gì `web_fetch`**.
- SSRF: `agent_card_url` phải qua `safe_url()` (đã có trong
  `core/tools/paths.py`).

## Phần 3 — Danh tính agent & uỷ quyền

### Data model

- `AgentIdentity`: `id`, `org_id`, `agent_id`, `subject` (định danh ổn định,
  ví dụ `agent:{org_id}:{agent_id}`), `allowed_audiences: list[str]`,
  `enabled`, `created_at`.

### Luồng token

1. Người dùng gọi agent bằng token của họ.
2. Backend thực hiện **token exchange nội bộ** (RFC 8693): phát token ngắn
   hạn cho `subject = agent identity`, `act = {sub: user_id}`, `aud` giới
   hạn đúng đích agent sắp gọi.
3. Agent dùng token đó khi gọi ra ngoài (A2A/MCP), không dùng token người dùng.
4. Audit ghi cả `actor_agent_identity_id` lẫn `on_behalf_of_user_id`.

### Cột thêm vào `audit_logs`

- `actor_agent_identity_id: str | None`
- `delegation_chain: JSON` — chuỗi `act` phẳng hoá, trả lời "ai uỷ quyền cho ai".

### Quy tắc

- Quyền hiệu lực = **giao** của quyền người dùng và quyền của agent identity.
  Agent không bao giờ có quyền cao hơn người gọi nó. Đây là bất biến quan
  trọng nhất của phần này — phải có test riêng.
- Token exchange chỉ nội bộ trong M16; liên kết với IdP ngoài để M17.

## Files to add

- `backend/app/a2a/__init__.py`, `server.py`, `client.py`, `card.py`
- `backend/app/models/agent_identity.py`, `backend/app/models/external_agent.py`
- `backend/app/core/auth/token_exchange.py`
- `backend/app/api/v1/routes/a2a.py`
- `backend/alembic/versions/00XX_a2a_and_agent_identity.py`
- `backend/tests/test_a2a_server.py`, `test_a2a_client.py`,
  `test_agent_identity_delegation.py`
- `frontend/app/agents/[id]/a2a/page.tsx` — bật/tắt phơi A2A

## Files to modify

- `backend/app/models/agent.py` — `a2a_exposed: bool = False`
- `backend/app/models/audit_log.py` — 2 cột uỷ quyền
- `backend/app/core/agent_loop.py` — dùng token đã exchange khi gọi ra ngoài
- `backend/app/core/tools/registry.py` — đăng ký `call_external_agent`
- `backend/app/main.py` — mount `/.well-known/agent-card.json`
- `backend/pyproject.toml` — SDK A2A nếu có bản Python ổn định; nếu chưa,
  implement thẳng theo spec HTTP (đừng chờ SDK)

## Suggested commit breakdown

1. `feat(agentos-m16): agent_identity model + internal token exchange (RFC 8693)`
2. `feat(agentos-m16): delegation chain columns in audit_log`
3. `feat(agentos-m16): permission intersection user ∩ agent identity`
4. `feat(agentos-m16): a2a agent card endpoint (opt-in per agent)`
5. `feat(agentos-m16): a2a task endpoints reusing agent_loop`
6. `feat(agentos-m16): external_agent registry model`
7. `feat(agentos-m16): call_external_agent tool with ssrf + untrusted guards`
8. `feat(agentos-m16): frontend a2a exposure toggle`
9. `test(agentos-m16): a2a server/client + delegation tests`

## Tests to write

`test_agent_identity_delegation.py` (quan trọng nhất):

- Quyền hiệu lực = giao của user và agent. User `viewer` + agent có tool
  `dangerous` → **vẫn bị chặn**.
- Audit ghi đủ `actor_agent_identity_id` + `on_behalf_of_user_id`.
- Token exchange ra token có `aud` đúng, TTL ngắn, `act` chứa user gốc.
- Token của agent **không** dùng lại được cho audience khác.

`test_a2a_server.py`:

- Agent `a2a_exposed=False` (mặc định) → **không** xuất hiện trong Agent Card.
- Request A2A không auth → 401; có auth → đi qua quota + guardrail như thường.
- Task A2A tạo ra audit + span đúng chuẩn M13.

`test_a2a_client.py`:

- `agent_card_url` trỏ IP nội bộ → bị `safe_url()` chặn.
- Output agent ngoài chứa prompt injection → bị `wrap_untrusted_if_flagged`.
- `call_external_agent` bị chặn nếu agent không có tier `network`.

## CI additions

- Fake A2A peer (Starlette app trong test) để test client mà không cần mạng.
- Validate Agent Card sinh ra khớp JSON Schema của spec A2A (pin schema vào repo).

## PR checklist

```
- [ ] a2a_exposed MẶC ĐỊNH False — phơi agent ra ngoài là hành động chủ động
- [ ] Request A2A vào đi qua đủ auth + quota + guardrail, không có đường tắt
- [ ] Quyền agent = GIAO của quyền user và agent identity (có test viewer + dangerous)
- [ ] Agent gọi ra ngoài dùng token đã exchange, KHÔNG dùng token người dùng
- [ ] Audit ghi đủ chuỗi uỷ quyền (actor_agent_identity_id + on_behalf_of_user_id)
- [ ] agent_card_url đi qua safe_url() — không SSRF
- [ ] Output agent ngoài coi là untrusted (wrap + redact) như web_fetch
- [ ] Agent Card validate được theo JSON Schema của spec A2A
- [ ] Đã đối chiếu lại spec A2A chính thức tại thời điểm implement
- [ ] pytest xanh, CI xanh
```