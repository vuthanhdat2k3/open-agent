# M3 — AuthZ / RBAC + Tool capability gate

## Branch
`agentos-v2/m3-authz-rbac` từ `main` (sau khi M2 merge).

Khuyến nghị chẻ 2 PR con: `agentos-v2/m3-01-permission-matrix` (route-level
RBAC) và `agentos-v2/m3-02-tool-risk-tier` (tool capability gate) — 2 phần
này độc lập nhau, có thể làm song song rồi merge lần lượt vào nhánh milestone.

## Scope
**Trong phạm vi**: permission matrix tĩnh, `require_permission` dependency
áp cho toàn bộ route hiện có, object-ownership check (404 cross-tenant),
mở rộng `ToolSpec` với `risk_tier`, gán risk tier cho tool hiện có, cột
`Agent.allowed_risk_tiers`, capability gate 2 lớp trong `agent_loop.py`.
**Ngoài phạm vi**: `ApprovalRequest`/human-approval thật (M4) — ở M3, tool
`requires_approval=True` chỉ cần bị chặn với lỗi rõ ràng, chưa cần flow
approve/reject.

## Depends on
M2 (cần `get_current_user` trả `role` qua `Membership`).

## Files to add
- `backend/app/core/authz/policy.py` (`PERMISSIONS` matrix,
  `has_permission(role, permission) -> bool`)
- `backend/app/core/authz/risk_tier.py` (enum `RiskTier`)
- `backend/tests/test_authz.py`
- `backend/tests/test_tool_capability_gate.py`

## Files to modify
- `backend/app/dependencies.py` — thêm `require_permission(permission: str)`
  factory; thêm `ensure_same_org(resource_org_id, ctx_org_id)` helper (raise
  `HTTPException(404)` nếu khác — không phải 403, để không lộ sự tồn tại của
  resource cross-tenant).
- `backend/app/api/v1/routes/*.py` (`agents.py, models.py, providers.py,
  mcp.py, workflows.py, chat.py, debug.py, sessions.py, files.py`) — thêm
  `Depends(require_permission("<resource>:<action>"))` vào từng route theo
  bảng mapping bên dưới, và gọi `ensure_same_org` ở route lấy theo id.
- `backend/app/core/tools/types.py` — thêm field `risk_tier: RiskTier`,
  `requires_approval: bool = False`, `timeout_s: float = 30.0`,
  `max_retries: int = 0` vào `ToolSpec`.
- `backend/app/core/tools/builtins.py`, `filesystem.py`, `memory.py`,
  `shell.py`, `sandbox.py`, `web_search.py` — gán `risk_tier` cho từng
  `ToolSpec(...)` theo bảng mapping trong `IMPLEMENTATION_PLAN.md` §M3 mục 5;
  `run_shell` thêm `requires_approval=True`.
- `backend/app/models/agent.py` — thêm cột
  `allowed_risk_tiers: Mapped[list[str]]` (JSON, default `["safe","read"]`).
- `backend/app/core/agent_loop.py` — trước khi execute tool: check (a)
  `tool.name in agent.tools` (đã có), (b) `tool.risk_tier in
  agent.allowed_risk_tiers` — nếu fail (b), trả `tool_result` dạng
  `error: tool '<name>' requires risk tier '<tier>' not granted to this agent`
  thay vì chạy; nếu `tool.requires_approval` và M4 chưa merge, trả
  `error: tool '<name>' requires approval (not yet supported)`.
- `backend/alembic/versions/00XX_add_agent_allowed_risk_tiers.py`

## Permission mapping (áp vào routes)

| Route | Permission |
|---|---|
| `POST/PATCH/DELETE /agents*` | `agents:create` / `agents:update` / `agents:delete` |
| `POST /agents/{id}/message`, workflow run | `agents:run` / `workflows:run` |
| `GET /agents*` | `agents:read` |
| `POST/PATCH/DELETE /providers*`, `/models*` | `providers:manage` |
| `POST/DELETE /mcp*` | `mcp:manage` |
| `POST/PATCH/DELETE /workflows*` | `workflows:create` / `workflows:update` / `workflows:delete` |
| `GET /debug*`, `/usage*` | `usage:read` |
| `POST /orgs/{id}/members`, `PATCH .../members/{uid}` | `org:manage_members` |
| `POST/DELETE /orgs/{id}/api-keys` | `org:manage_api_keys` |

(Đối chiếu `PERMISSIONS` matrix trong `ARCHITECTURE.md` §4.2 khi implement —
bảng trên là mapping route→permission, không phải permission→role.)

## Step-by-step
1. Viết `RiskTier` enum + `PERMISSIONS` matrix trước (thuần data, không phụ
   thuộc gì, dễ unit test độc lập).
2. Viết `require_permission`, áp thử vào 1 route (`agents.py`) để xác nhận
   pattern đúng trước khi áp hàng loạt.
3. Áp hàng loạt theo bảng mapping, chạy `pytest` sau mỗi file để bắt lỗi sớm
   (nhiều test cũ sẽ cần thêm auth header/token giả trong request test).
4. Mở rộng `ToolSpec`, gán risk tier từng tool, chạy lại toàn bộ
   `test_tools.py` (đảm bảo M0 đã fix async không bị regress).
5. Thêm capability gate 2 lớp vào `agent_loop.py`, viết test riêng.
6. Cập nhật `backend/scripts/seed.py` để agent seed mặc định có
   `allowed_risk_tiers` hợp lý (không set `dangerous`/`execute` mặc định).

## Suggested commit breakdown
1. `feat(agentos-m3): risk tier enum + static permission matrix`
2. `feat(agentos-m3): require_permission dependency + ensure_same_org helper`
3. `feat(agentos-m3): apply permission checks to agent/workflow/provider/mcp/org routes`
4. `feat(agentos-m3): add risk_tier/requires_approval/timeout to ToolSpec`
5. `feat(agentos-m3): assign risk tiers to all builtin tools, gate run_shell behind approval`
6. `feat(agentos-m3): add allowed_risk_tiers to Agent model + migration`
7. `feat(agentos-m3): enforce two-layer capability gate in agent_loop`
8. `test(agentos-m3): authz + tool capability gate tests`

## Tests to write
- `test_authz.py`: viewer → 403 trên `POST /agents`; developer → 403 trên
  `PATCH /orgs/{id}/members/{uid}`; owner → mọi permission pass; user org A
  gọi resource org B theo id → 404 (không phải 403).
- `test_tool_capability_gate.py`: agent với `allowed_risk_tiers=["safe"]` gọi
  tool `risk_tier=write` → bị chặn với lỗi rõ ràng, không throw exception
  không kiểm soát; agent với `allowed_risk_tiers` đủ → tool chạy bình thường;
  `run_shell` luôn bị chặn dù risk tier cho phép, vì `requires_approval=True`
  chưa có M4.

## CI additions
Không cần job mới; đảm bảo test auth (M2) + authz (M3) chạy trong cùng job
`backend` hiện có, tổng thời gian CI vẫn hợp lý (nếu integration test chậm
do nhiều DB fixture, cân nhắc `pytest-xdist` — optional, không bắt buộc).

## PR checklist
```
- [ ] Permission matrix + require_permission áp dụng cho toàn bộ route liệt kê ở bảng mapping
- [ ] Cross-tenant access trả 404 (không phải 403), có test xác nhận
- [ ] ToolSpec có risk_tier/requires_approval/timeout_s/max_retries
- [ ] Toàn bộ builtin tool đã gán risk_tier đúng theo bảng trong IMPLEMENTATION_PLAN.md
- [ ] run_shell bị chặn mặc định (requires_approval), có test xác nhận
- [ ] agent_loop chặn tool ngoài allowed_risk_tiers của agent, trả lỗi rõ ràng thay vì crash
- [ ] pytest xanh (kể cả test cũ đã cập nhật thêm auth), CI xanh
```
