# AgentOS v2 — Implementation Plan

> Kế hoạch triển khai chi tiết theo milestone cho agent coding thực thi. Đọc
> `ARCHITECTURE.md` trước để hiểu "why". Mỗi milestone độc lập kiểm thử được,
> có acceptance criteria rõ ràng, và khai báo dependency với milestone trước
> để agent biết thứ tự bắt buộc vs. có thể làm song song.
>
> Quy ước: đường dẫn tương đối tới `backend/app/` hoặc `frontend/` trừ khi
> ghi rõ khác. Mọi milestone kết thúc bằng `pytest` xanh (backend) và
> `npm run build` xanh (frontend nếu có đổi).
>
> Mỗi milestone có 1 file "implement chi tiết" riêng trong
> [`tasks/`](tasks/) (`tasks/M<n>-<slug>.md`) — nêu chính xác file cần
> sửa, breakdown commit, và test/CI phải viết. File này (`IMPLEMENTATION_PLAN.md`)
> là bản đồ tổng — mọi thực thi thật sự đi theo file trong `tasks/`.

---

## Git Workflow & PR Policy (áp dụng cho MỌI milestone/task bên dưới)

Không có ngoại lệ: **mỗi task nhỏ nhất có thể review độc lập được** (tối đa
= 1 milestone, tối thiểu = 1 mục trong "Suggested commit breakdown" của file
`tasks/M<n>-*.md`) phải đi qua đúng quy trình sau — dù người thực thi là
người hay agent.

### 1. Nhánh (branch)

- Không commit thẳng vào `main`. Mỗi milestone (hoặc mỗi sub-task nếu
  milestone bị chẻ nhỏ để dễ review) tạo **1 nhánh riêng** từ điểm mới nhất
  của `main` (hoặc từ nhánh milestone trước đó nếu milestone sau phụ thuộc
  và chưa merge — xem "Merge order" bên dưới).
- Quy ước tên: `agentos-v2/m<n>-<slug>`, ví dụ:
  `agentos-v2/m0-foundation-fixes`, `agentos-v2/m3-authz-rbac`. Nếu 1
  milestone bị chẻ thành nhiều PR (khuyến nghị cho M1–M6 vì khối lượng lớn):
  `agentos-v2/m3-01-permission-matrix`, `agentos-v2/m3-02-tool-risk-tier`, ...
  (số thứ tự 2 chữ số để sort đúng thứ tự trên GitHub).
- Không đặt tên nhánh chung chung (`fix`, `wip`, `update`).

### 2. Commit

- Chia commit theo **"Suggested commit breakdown"** trong từng file
  `tasks/M<n>-*.md` — mỗi commit là 1 thay đổi hoàn chỉnh, tự chạy test được
  (không bắt buộc pass toàn bộ CI ở mỗi commit trung gian, nhưng không được
  để lại code chết/half-broken qua nhiều commit không lý do).
- Message theo **Conventional Commits**, đúng style đã dùng trong repo hiện
  tại (`feat(scope): ...`, `fix(scope): ...`, `test(scope): ...`,
  `docs(scope): ...`, `chore(scope): ...`) — scope = tên milestone viết tắt,
  ví dụ `feat(agentos-m1): add organization/user/membership models`.
- Không gộp nhiều mối quan tâm không liên quan vào 1 commit (vd không trộn
  "fix bug X" với "thêm CI job Y" trong cùng 1 commit).

### 3. Pull Request

- Mỗi nhánh kết thúc bằng **1 PR về `main`** (hoặc về nhánh milestone cha nếu
  đang chẻ nhỏ theo sub-task — merge sub-task PR vào nhánh milestone trước,
  rồi 1 PR tổng milestone → `main` sau khi toàn bộ sub-task xong).
- PR description **bắt buộc** dùng đúng "PR checklist" trong file
  `tasks/M<n>-*.md` tương ứng (mục tiêu, phạm vi, test đã thêm, acceptance
  criteria nào đã đạt — copy nguyên checklist, tick từng dòng).
- PR phải xanh CI (`.github/workflows/ci.yml`, xem M0) trước khi merge —
  không merge khi CI đỏ, không dùng `--no-verify`/skip check.
- Không tự-approve nếu có người review khác trong team; nếu chỉ có 1
  agent/người thực thi, vẫn phải để CI là gate bắt buộc (không thay thế cho
  review, nhưng là điều kiện cần).

### 4. Merge order

Merge theo đúng thứ tự dependency đã khai báo ở mỗi milestone (xem sơ đồ
"Thứ tự thực thi khuyến nghị" cuối file này). Không merge M3 trước M2 dù code
có vẻ độc lập — migration/model của milestone sau thường giả định milestone
trước đã có trong `main` để tránh xung đột migration Alembic (2 milestone
cùng thêm revision song song → conflict revision graph).

---

## M0 — Sửa lỗi nền tảng + CI tối thiểu (bắt buộc làm trước, không phụ thuộc gì)

> 📄 Chi tiết: [`tasks/M0-foundation-fixes.md`](tasks/M0-foundation-fixes.md)

**Mục tiêu**: dọn nợ kỹ thuật đã phát hiện, có CI để mọi milestone sau không
regress trong im lặng.

**Việc cần làm**:
1. Fix bug async/sync trong tool: đổi `def` → `async def` cho:
   - `backend/app/core/tools/builtins.py:26` (`_read_attachment`)
   - `backend/app/core/tools/filesystem.py:26,44,76` (`_write_file`,
     `_list_dir`, `_search_files`)
   Không cần đổi call site (`agent_loop.py`, `workflow/engine.py` đã `await`
   sẵn, đúng theo type hint `Awaitable[str]` trong `ToolSpec.run`).
2. Fix test `test_save_and_call_memory` (`backend/tests/test_tools.py`) đang
   gọi `save_memory`/`call_memory` bằng schema cũ (`key`/`value`) — cập nhật
   lời gọi test theo schema hiện tại (`memory_type`/`attribute`/`value` +
   `agent_id` trong `ToolContext`).
3. Xoá config chết `loop_warn`, `loop_block`, `loop_circuit` khỏi
   `backend/app/config.py` (sẽ được thay bằng cơ chế thật ở M4 với tên field
   mới, không tái dùng tên cũ để tránh nhầm "đã có sẵn").
4. Thêm `.github/workflows/ci.yml`:
   - Job `backend`: `pip install -e .[dev]`, `ruff check .`, `pytest -q`.
   - Job `frontend`: `npm ci`, `npm run lint`, `npx tsc --noEmit`, `npm run build`.
5. Thêm `/healthz` (trả 200 ngay, không chạm DB) vào `backend/app/main.py`.

**Acceptance**: `pytest` 5/5 pass; CI workflow chạy xanh trên PR test.

---

## M1 — Identity & Multi-tenancy (Organization / User / Membership)

> 📄 Chi tiết: [`tasks/M1-identity-tenancy.md`](tasks/M1-identity-tenancy.md)

**Phụ thuộc**: M0.

**Việc cần làm**:
1. Models mới (`backend/app/models/`):
   - `organization.py`: `Organization(id, name, slug unique, created_at)`
   - `user.py`: `User(id, email unique, hashed_password nullable, display_name,
     is_active, created_at)`
   - `membership.py`: `Membership(id, org_id FK, user_id FK, role Enum,
     invited_by nullable, created_at)`, unique constraint `(org_id, user_id)`
   - `Role` enum (`owner, admin, developer, viewer`) — đặt trong
     `backend/app/models/role.py` để dùng chung models + authz policy.
2. Migration Alembic:
   - Tạo 3 bảng trên.
   - Thêm cột `org_id` (FK, nullable=True tạm thời để migrate an toàn, sau đó
     `NOT NULL` ở migration kế) + `created_by_user_id` (nullable) vào:
     `agent, model, provider, mcp_server, workflow, session, message,
     usage_event, uploaded_file, agent_memory, session_memory`.
   - **Data migration script** (trong cùng migration hoặc script riêng
     `backend/scripts/migrate_to_multiuser.py`): tạo 1 `Organization` mặc
     định ("Default Organization"), 1 `User` owner từ env
     (`OPENAGENT_BOOTSTRAP_ADMIN_EMAIL` / `..._PASSWORD`), gán toàn bộ row
     hiện có vào `org_id` đó, tạo `Membership(role=owner)`.
   - Migration thứ hai: đổi `org_id` sang `NOT NULL` sau khi backfill xong.
3. Repository layer: `backend/app/repositories/base.py` — thêm tham số bắt
   buộc `org_id` cho mọi hàm list/get (không optional) để **không thể quên
   filter tenant** ở bất kỳ repo con nào kế thừa.
4. `backend/app/dependencies.py`: thêm `get_current_org_id(request) -> str`
   (đọc từ JWT claims hoặc header `X-Org-Id` cho API key đa-org) để inject
   vào mọi service call.

**Acceptance**: migration chạy trên DB có data cũ (test bằng cách seed DB
kiểu cũ rồi upgrade) → toàn bộ resource cũ thuộc về Default Organization, có
thể query lại đúng qua `org_id`.

---

## M2 — AuthN (OAuth2/OIDC + JWT + API key)

> 📄 Chi tiết: [`tasks/M2-authn.md`](tasks/M2-authn.md)

**Phụ thuộc**: M1.

**Việc cần làm**:
1. Thêm dependency: `authlib`, `python-jose[cryptography]` (hoặc `pyjwt`),
   `argon2-cffi`.
2. Models: `oauth_account.py`, `refresh_token.py`, `api_key.py` (schema theo
   `ARCHITECTURE.md` §3.1).
3. `backend/app/core/auth/`:
   - `jwt.py`: sign/verify access token (RS256/EdDSA, keypair trong env hoặc
     file — tài liệu hoá rotate key sau).
   - `password.py`: argon2 hash/verify.
   - `oauth.py`: Google + GitHub OIDC client config qua `authlib`.
   - `api_key.py`: generate (`oa_live_<32 random bytes base62>`), hash
     (sha256, không cần argon2 vì đã random đủ entropy), verify.
4. Routes mới `backend/app/api/v1/routes/auth.py`:
   - `POST /auth/register`, `POST /auth/login`, `POST /auth/refresh`,
     `POST /auth/logout`, `GET /auth/me`
   - `GET /auth/oauth/{provider}/authorize`, `GET /auth/oauth/{provider}/callback`
   - `POST /orgs`, `GET /orgs/{id}/members`, `POST /orgs/{id}/members`
     (invite theo email), `PATCH /orgs/{id}/members/{user_id}` (đổi role),
     `DELETE /orgs/{id}/members/{user_id}`
   - `POST/GET/DELETE /orgs/{id}/api-keys`
5. `backend/app/dependencies.py`: `get_current_user` — thử JWT trước, fallback
   API key; raise 401 nếu cả hai đều fail. **Giữ nguyên** `verify_api_key`
   (machine mode cũ) cho route nội bộ/dev không đổi.
6. Refresh token rotation: mỗi lần `/auth/refresh` được gọi, revoke token cũ
   (set `revoked_at`), issue token mới, set `replaced_by_id` — chống replay
   sau khi token bị đánh cắp và dùng lại token cũ.

**Acceptance**: đăng ký/đăng nhập email+password hoạt động end-to-end (test
tích hợp); refresh token rotate đúng (dùng lại token cũ sau khi refresh phải
bị từ chối); OAuth callback tạo `User`+`OAuthAccount` nếu chưa tồn tại.

---

## M3 — AuthZ / RBAC + Tool capability gate

> 📄 Chi tiết: [`tasks/M3-authz-rbac.md`](tasks/M3-authz-rbac.md)

**Phụ thuộc**: M2.

**Việc cần làm**:
1. `backend/app/core/authz/policy.py`: `PERMISSIONS` matrix (theo
   `ARCHITECTURE.md` §4.2), hàm `has_permission(role, permission) -> bool`.
2. `backend/app/dependencies.py`: `require_permission(permission: str)` —
   factory trả về FastAPI dependency, tra `Membership.role` của
   `current_user` trong `current_org`.
3. Áp `require_permission(...)` vào toàn bộ route hiện có theo domain (ví dụ
   `agents:create`, `agents:run`, `workflows:run`, `providers:manage`,
   `mcp:manage`, `org:manage_members`) — rà từng file trong
   `backend/app/api/v1/routes/`.
4. Object-ownership check: helper `ensure_same_org(resource.org_id,
   ctx.org_id)` gọi trong mọi route lấy resource theo id (403 nếu khác org —
   **không phải** 404, để tránh lộ khác biệt giữa "không tồn tại" và "không
   có quyền" chỉ ở nội bộ log, nhưng response HTTP vẫn nên trả 404 ra ngoài để
   không rò rỉ sự tồn tại của resource cross-tenant — quyết định: trả 404).
5. Mở rộng `ToolSpec` (`core/tools/types.py`) thêm `risk_tier: RiskTier`,
   `requires_approval: bool = False`, `timeout_s: float = 30.0`,
   `max_retries: int = 0`. Gán risk tier cho từng tool hiện có:
   - `safe`: `memory_recall`, `memory_store`, `call_memory`, `save_memory`
   - `read`: `read_attachment`, `list_dir`, `search_files`, `web_fetch`
   - `write`: `write_file`
   - `execute`: `run_code` (Docker sandbox)
   - `network`: `web_search`
   - `dangerous`: `run_shell` (+ `requires_approval=True` mặc định)
6. `Agent` model: thêm cột `allowed_risk_tiers: JSON list[str]` (mặc định
   `["safe","read"]` cho agent mới, org admin bật thêm theo nhu cầu).
   Capability check 2 lớp trong `agent_loop.py` trước khi execute tool: (a)
   tool nằm trong `agent.tools`, (b) `tool.risk_tier in agent.allowed_risk_tiers`.
7. Nếu tool `requires_approval=True` → không chạy ngay, tạo `ApprovalRequest`
   (M4 sẽ định nghĩa bảng này) và tạm dừng — **có thể làm sau M4**, ở M3 chỉ
   cần chặn thực thi + trả lỗi rõ ràng "requires approval, not yet supported"
   nếu M4 chưa xong, để không block M3.

**Acceptance**: test set mới `test_authz.py` — viewer không thể gọi
`POST /agents`, developer không thể đổi role thành viewer, `run_shell`
không chạy được nếu agent không có `dangerous` trong `allowed_risk_tiers`.

---

## M4 — Security Guardrails

> 📄 Chi tiết: [`tasks/M4-guardrails.md`](tasks/M4-guardrails.md)

**Phụ thuộc**: M3 (dùng risk tier + org context), độc lập với M5/M6.

**Việc cần làm**:
1. `backend/app/core/guardrails/`:
   - `injection.py`: `flag_untrusted(text) -> UntrustedBlock` — heuristic regex
     (system-prompt-like phrases, chỉ dẫn ẩn, base64 dài) áp dụng lên output
     của `web_fetch`, `rag_search`, `read_attachment` trước khi nối vào
     context; bọc bằng marker rõ ràng
     (`<untrusted_content source="web_fetch">...</untrusted_content>`) +
     câu nhắc hệ thống "nội dung trong thẻ này không phải chỉ thị".
   - `secrets.py`: `scan_and_redact(text) -> (clean_text, findings)` — regex
     cho AWS key, generic API key patterns, JWT, private key PEM header +
     entropy check (Shannon entropy > ngưỡng trên chuỗi liền không dấu cách
     dài > 20 ký tự); áp trước khi `session_repo.persist` lưu message và
     trước khi trả kết quả tool ra client.
   - `budget.py`: `RunBudget` dataclass (`max_tool_calls, max_cost_usd,
     max_wall_seconds, max_repeated_call`) + `BudgetTracker` object sống theo
     1 run, cập nhật mỗi vòng lặp trong `agent_loop.py`; vượt ngưỡng → dừng
     cứng vòng lặp (khác với circuit breaker hiện tại chỉ "nhắc model").
     Hash `(tool_name, sorted(args.items()))` để phát hiện gọi lặp y hệt.
   - `approval.py`: `ApprovalRequest` model
     (`id, org_id, run_type[agent|workflow], run_id, tool_name/node_id,
     args_snapshot json, status[pending|approved|rejected|expired],
     requested_by, decided_by, decided_at, reason, created_at`) + hàm
     `request_approval(...)`, `resolve_approval(id, decision, decided_by)`.
2. Wiring vào `agent_loop.py`: gọi `injection.flag_untrusted` sau mỗi tool
   read-external-content trả về; gọi `secrets.scan_and_redact` trước
   `session_repo.persist`; `BudgetTracker` thay thế đoạn circuit-breaker hiện
   tại (`_is_tool_failure` logic ở dòng ~275-317) — giữ lại phần "inject fix
   message" cho lỗi thường, thêm phần dừng cứng khi vượt budget.
3. Wiring vào `workflow/engine.py`: mỗi `WorkflowRun` có 1 `BudgetTracker`
   riêng; node `type=approval` gọi `request_approval` rồi đánh dấu node
   `status=waiting_approval`, không cho downstream chạy tới khi resolve.
4. API mới: `GET /api/v1/approvals` (list pending theo org),
   `POST /api/v1/approvals/{id}/decide` (`{decision, reason}`,
   permission `approvals:decide`, mặc định chỉ `admin`/`owner`).
5. SSE event mới `approval_required` phát ra trong stream chat/workflow khi
   1 run bị pause chờ duyệt.
6. Thay `eval()` trần trong `core/workflow/engine.py` (dòng ~16-20) bằng thư
   viện `simpleeval` (thêm dependency) — whitelist rõ operator/hàm cho phép.
7. Siết `core/tools/sandbox.py`: thêm flag Docker
   `--security-opt no-new-privileges`, `--pids-limit=64`, `--read-only` +
   `--tmpfs /work:rw,size=64m`, giữ `--network none` mặc định (đã có).

**Acceptance**: test giả lập agent gọi cùng 1 tool-call 10 lần liên tiếp →
budget tracker dừng ở ngưỡng cấu hình; test injection filter bọc đúng nội
dung web_fetch; test approval flow: tool `dangerous` tạo `ApprovalRequest`,
`POST decide` với `approved` cho phép resume, `rejected` kết thúc run với lỗi
rõ ràng.

---

## M5 — Agent Core v2 (Subagent Task model + Orchestrator + Tool registry v2)

> 📄 Chi tiết: [`tasks/M5-agent-core-v2.md`](tasks/M5-agent-core-v2.md)

**Phụ thuộc**: M3 (risk tier), độc lập với M4/M6 (có thể làm song song với
người khác trong team nếu cần).

**Việc cần làm**:
1. Model `task.py`: `Task(id, org_id, parent_task_id nullable, root_run_id,
   agent_id, goal, status Enum[pending,running,succeeded,failed,cancelled],
   result nullable, cost_usd, token_usage json, depth, started_at, finished_at)`.
2. Sửa `call_agent` (`core/tools/builtins.py`) để mỗi lần gọi:
   - Tạo `Task` row trước khi chạy subagent.
   - Chạy `agent_loop` con như hiện tại (giữ nguyên depth-gate
     `max_agent_depth`).
   - Cập nhật `Task.status/result/cost_usd` khi xong.
   - Trả kết quả cho agent cha như hiện tại (không đổi contract tool).
3. `Agent.kind: Literal["worker","orchestrator"] = "worker"` (cột mới).
   Orchestrator: system prompt bổ sung hướng dẫn model tự chia goal thành
   sub-task list (structured output, ví dụ JSON list `{agent_id, goal}` hoặc
   để model tự gọi nhiều lần `call_agent` — **khuyến nghị**: không cần cơ chế
   decompose riêng, orchestrator chỉ là agent có system-prompt phù hợp + được
   cấp quyền gọi nhiều agent qua `call_agent` nhiều lần trong 1 loop; giữ đơn
   giản, tránh over-engineer 1 planner riêng ở v1).
4. Tool registry v2: validate `args` bằng `jsonschema.validate(args,
   spec.input_schema)` trước khi gọi `spec.run` trong cả `agent_loop.py` và
   `workflow/engine.py` — bắt lỗi schema sớm, trả `error: invalid arguments`
   thay vì để tool tự crash.
5. Debug API mới: `GET /api/v1/debug/tasks/{root_run_id}` — trả cây `Task`
   (parent→children) để frontend vẽ delegation tree.

**Acceptance**: workflow gọi agent A → A gọi `call_agent` tới B hai lần song
song (qua `asyncio.gather` nếu model phát nhiều tool-call cùng lúc, hoặc tuần
tự nếu model gọi lần lượt) → `GET /debug/tasks/{root}` trả đúng cây 3 node
(A, B1, B2) với cost/status chính xác.

---

## M6 — Workflow Engine v2 (Durable execution + queue)

> 📄 Chi tiết: [`tasks/M6-workflow-engine-v2.md`](tasks/M6-workflow-engine-v2.md)

**Phụ thuộc**: M4 (approval node cần `ApprovalRequest`), M5 (agent node dùng
Task model để log subagent trong workflow).

**Việc cần làm**:
1. Thêm Redis + `arq` vào `backend/pyproject.toml`.
2. Models: `workflow_run.py`
   (`WorkflowRun(id, org_id, workflow_id, status, input json, started_at,
   finished_at, triggered_by_user_id)`), `workflow_node_run.py`
   (`WorkflowNodeRun(id, workflow_run_id, node_id, status, attempt, input
   json, output json, error, started_at, finished_at)`).
3. `backend/app/core/workflow/engine.py`: sau mỗi node hoàn thành, ghi 1 dòng
   `WorkflowNodeRun` (không thay đổi thuật toán wavefront scheduler hiện có —
   chỉ thêm persistence tại điểm complete/fail của mỗi node).
4. Config `workflow_execution_mode: Literal["inline","queued"] = "inline"`
   (`config.py`). Khi `queued`: thay vì `asyncio.create_task(run_node(...))`
   trực tiếp, engine enqueue 1 arq job `run_workflow_node(workflow_run_id,
   node_id)`; job đọc state từ DB, chạy node, ghi kết quả, rồi tự enqueue các
   node kế tiếp trở nên `ready` — biến "scheduler trong 1 process" thành
   "scheduler dựa trên DB state + queue", chịu được worker restart.
5. `backend/app/worker.py` (entry point mới): `arq` worker process, đăng ký
   job `run_workflow_node`, `run_agent_task` (cho M5 subagent chạy queued nếu
   cần), cấu hình Redis URL từ settings.
6. Node type mới:
   - `type="approval"`: gọi `guardrails.approval.request_approval`, trạng
     thái node `waiting_approval` tới khi resolve.
   - `type="sub_workflow"`: field `workflow_id` trỏ tới workflow khác, engine
     gọi đệ quy `WorkflowEngine.run(child_workflow_id, input)`.
   - Retry: field `retry: {max_attempts:int, backoff_s:float}` trên node —
     engine bắt exception, retry theo backoff trước khi mark `error`.
   - Timeout: field `timeout_s` trên node — wrap `asyncio.wait_for`.
7. `docker-compose.yml` (root, mới): service `worker` chạy
   `python -m app.worker`, service `redis`.

**Acceptance**: workflow 5 node (2 song song → merge → agent → approval) chạy
được cả `inline` và `queued` mode cho cùng kết quả; kill worker container
giữa chừng 1 job `queued` → khởi động lại worker → workflow tự resume từ node
chưa xong (không chạy lại node đã `succeeded`).

---

## M7 — Observability

> 📄 Chi tiết: [`tasks/M7-observability.md`](tasks/M7-observability.md)

**Phụ thuộc**: không phụ thuộc milestone nghiệp vụ nào, có thể làm song song
từ M1 trở đi; nên làm sau M4-M6 để có đủ điểm gắn span (tool call, node,
approval) đáng đo.

**Việc cần làm**:
1. Thêm dependency: `structlog`, `opentelemetry-sdk`,
   `opentelemetry-instrumentation-fastapi`, `opentelemetry-exporter-otlp`,
   `prometheus-fastapi-instrumentator`.
2. `backend/app/core/observability/logging.py`: cấu hình `structlog` JSON
   renderer + context vars `request_id/run_id/org_id/user_id`; middleware
   gán `request_id` (uuid4) mỗi request.
3. `backend/app/core/observability/tracing.py`: init OTel TracerProvider,
   OTLP exporter (endpoint từ `OTEL_EXPORTER_OTLP_ENDPOINT`); span thủ công
   quanh: 1 iteration của agent loop, 1 tool call, 1 workflow node, 1 sandbox
   exec — attribute `org_id, agent_id, tool_name, risk_tier`.
4. `backend/app/core/observability/metrics.py`: custom `Counter`/`Histogram`
   (`tool_calls_total{tool_name,status}`, `tool_call_duration_seconds`,
   `agent_run_cost_usd_total{org_id}`, `workflow_run_duration_seconds`,
   `sandbox_executions_total{status}`, `queue_depth`); mount
   `Instrumentator().instrument(app).expose(app)` cho `/metrics`.
5. `backend/app/models/audit_log.py`:
   `AuditLog(id, org_id, actor_user_id nullable, actor_api_key_id nullable,
   action, resource_type, resource_id, metadata json, ip, created_at)` —
   append-only, ghi tại: login, đổi role, tạo/revoke API key, tool
   `dangerous` execute, approval decide.
6. `observability/` (thư mục mới ở root repo, không phải trong `backend/`):
   - `docker-compose.observability.yml` hoặc profile trong compose chính:
     `otel-collector, prometheus, grafana, loki, promtail`.
   - `observability/grafana/dashboards/*.json`: dashboard "Usage & Cost theo
     org", "Latency & Error rate", "Queue & Worker health".
   - `observability/prometheus/alerts.yml`: rule cơ bản (error rate > 5%
     /5m, `queue_depth` > N trong 10 phút, `sandbox_executions_total{status=
     "error"}` rate cao).

**Acceptance**: chạy 1 workflow → thấy trace đầy đủ trên Grafana Tempo/Jaeger
(nếu dùng Tempo) với span cha-con đúng agent→tool→sandbox; `/metrics` trả về
đúng counter đã tăng; audit log có dòng ghi khi 1 API key bị revoke.

---

## M8 — Deployment & Scale readiness

> 📄 Chi tiết: [`tasks/M8-deployment.md`](tasks/M8-deployment.md)

**Phụ thuộc**: M6 (cần `worker`/Redis), M7 (observability stack), nên làm
cuối cùng để gom mọi service đã có thành 1 compose file hoàn chỉnh.

**Việc cần làm**:
1. Chuyển default DB dev → Postgres trong compose (giữ SQLite chỉ như tuỳ
   chọn test nhanh không cần Docker, tài liệu rõ trong README).
2. `docker-compose.yml` gốc (mới, hiện repo chưa có ở root):
   services: `frontend, api, worker, postgres, redis, qdrant, rag-service,
   mcp-drive-server (profile optional), otel-collector, prometheus, grafana,
   loki, promtail` — dùng compose `profiles` để observability + mcp-drive
   là optional (`docker compose --profile observability up`).
3. Healthcheck: `/healthz` (đã có từ M0) + `/readyz` (check DB connect +
   Redis ping) — dùng trong `healthcheck:` của compose cho `api`/`worker`.
4. `.env.example` gốc: gộp toàn bộ biến mới (JWT keys, OAuth client
   id/secret, Redis URL, OTEL endpoint, bootstrap admin email/password).
5. CI mở rộng (từ M0): thêm job build Docker image cho `api`/`worker`/
   `frontend`, chạy `docker compose config` để validate compose file trên
   PR (không cần push image ở v1, chỉ validate build).
6. Cập nhật `README.md` + `docs/ARCHITECTURE.md` gốc để trỏ sang
   `docs/agentos-v2/` là kiến trúc hiện hành (đánh dấu doc cũ là "v1,
   superseded").

**Acceptance**: `docker compose up` từ máy sạch (không cài gì ngoài Docker)
dựng được toàn bộ hệ thống, `api` và `worker` báo healthy, đăng nhập được qua
UI, chạy được 1 workflow queued end-to-end.

---

## M9 — Frontend

> 📄 Chi tiết: [`tasks/M9-frontend.md`](tasks/M9-frontend.md)

**Phụ thuộc**: chạy song song theo backend milestone tương ứng (M9.1 cần M2,
M9.2 cần M3, M9.3 cần M4, M9.4 cần M5/M6, M9.5 cần M7).

1. **Auth UI**: `/login`, `/register`, `/oauth/callback/[provider]` — form
   Zod + React Hook Form theo pattern hiện có; lưu access token in-memory
   (không localStorage, chống XSS), refresh token qua httponly cookie do
   backend set.
2. **Org & member management**: `/settings/members` (list/invite/đổi role),
   `/settings/api-keys` (tạo/revoke, hiện full key 1 lần).
3. **Approval inbox**: `/approvals` — list `ApprovalRequest` pending theo
   org, nút Approve/Reject + lý do; badge số lượng pending trên nav.
4. **Debug nâng cấp**: cây delegation (`Task`) dạng tree view trong
   `/debug`; workflow run history hiện `WorkflowNodeRun` per-node
   status/timing thay vì chỉ trạng thái cuối.
5. **Tool risk badge**: trong tool picker của `/agents`, hiện badge màu theo
   `risk_tier` (safe=xám, read=xanh, write=vàng, execute=cam, network=tím,
   dangerous=đỏ + icon cảnh báo) lấy từ endpoint tool registry mở rộng.
6. Sửa nợ kỹ thuật đã phát hiện trong lần review trước (không phải yêu cầu
   mới, tiện làm cùng đợt): `stores/index.ts` bỏ `any[]` cho
   `WorkflowState.nodes/edges` (dùng lại `GraphNode`/`GraphEdge` từ
   `types/index.ts`), `hooks/index.ts` gõ kiểu `mutationFn` bằng type suy ra
   từ Zod schema thay vì `any`.

**Acceptance**: luồng thủ công — đăng ký → tạo org → mời thêm 1 thành viên
role `developer` → thành viên đó tạo agent với tool `dangerous` → thấy
approval xuất hiện ở `/approvals` cho `admin` duyệt → workflow tiếp tục
chạy.

---

## Thứ tự thực thi khuyến nghị (nếu 1 agent làm tuần tự)

```
M0 → M1 → M2 → M3 → ┬→ M4 → M6 → M8
                     └→ M5 ────┘
                  (M7 xen kẽ từ sau M3, hoàn thiện dần)
                  (M9 bám theo từng M tương ứng ở backend)
```

Không có milestone nào là "optional" theo yêu cầu ban đầu (auth, RBAC,
guardrail, monitor, scale, deploy đều được yêu cầu rõ) — nhưng nếu cần ra bản
dùng được sớm hơn, thứ tự M0-M3 đã đủ để có 1 hệ thống multi-user an toàn cơ
bản; M4-M9 nâng dần lên chuẩn "dự án lớn".
