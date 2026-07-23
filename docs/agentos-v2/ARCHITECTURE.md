# OpenAgent → AgentOS v2 — Target Architecture

> Tài liệu này mô tả **kiến trúc đích** sau khi nâng cấp OpenAgent từ "personal
> multi-agent tool" thành một **AgentOS đa người dùng, sẵn sàng scale và
> deploy**. Đi kèm với `IMPLEMENTATION_PLAN.md` (kế hoạch triển khai theo
> milestone) — tài liệu này là phần "what/why", plan là phần "how/when".

Quyết định khung đã chốt với chủ dự án:

| Trục quyết định | Lựa chọn |
|---|---|
| Tenancy | **Multi-user + RBAC** (Organization → Membership → Role) |
| Deploy target | **Docker Compose, 1 host**, thiết kế để lên Kubernetes sau mà không phải viết lại app |
| Sandbox code execution | **Docker hardened** (không phải microVM) |
| Auth | **OAuth2/OIDC + JWT** (không chỉ API key phẳng như hiện tại) |

Các quyết định kỹ thuật khác (queue, observability stack, DB) được chọn theo
tiêu chí "đơn giản nhất mà vẫn đúng chuẩn production" — nêu rõ lý do bên dưới,
có thể revisit nếu bạn muốn khác.

---

## 1. Nguyên tắc thiết kế

1. **Không phá vỡ layering hiện có** (routes → services → repositories →
   models). Mọi thứ mới (auth, RBAC, guardrail, observability) là **cross-cutting
   concerns** gắn vào layer hiện có qua FastAPI dependencies + middleware, không
   viết lại core engine.
2. **Stateless API, stateful workers.** API server không giữ state của
   long-running run — mọi agent run / workflow run dài được **durable** (ghi
   DB + queue) để chịu được restart, và scale ngang được bằng cách thêm worker.
3. **Capability trước, không phải "tin tưởng ngầm".** Mọi tool phải khai báo
   risk tier; mọi role phải khai báo risk tier được phép; mọi hành động nguy
   hiểm phải có audit log. Đây là gap lớn nhất hiện tại (không có capability
   gate thật, chỉ có filter theo tên tool trong `agent.tools`).
4. **Guardrail là lớp riêng, không lẫn vào business logic.** Prompt-injection
   filter, secret scanner, budget circuit breaker, approval gate đều là các
   module độc lập trong `core/guardrails/`, được agent loop & workflow engine
   gọi tại các điểm cố định — dễ test, dễ bật/tắt theo policy.
5. **Observability là first-class, không phải thêm sau.** Mọi run (agent,
   subagent, tool call, workflow node) đều có `trace_id`/`run_id` xuyên suốt để
   nhìn thấy toàn bộ cây thực thi trong debug UI và trong Grafana.
6. **Multi-tenant an toàn bằng thiết kế, không bằng kỷ luật code.** Row-level
   scoping theo `org_id` được enforce ở **repository layer** (base repository
   luôn require org_id trong query), không dựa vào việc mỗi service tự nhớ
   filter.

---

## 2. Sơ đồ tổng quan

```
                              ┌─────────────────────┐
                              │      Frontend        │
                              │  Next.js (App Router) │
                              └──────────┬───────────┘
                                         │ HTTPS
                              ┌──────────▼───────────┐
                              │     API Gateway       │      (FastAPI, stateless,
                              │  auth / RBAC / rate-  │       horizontally replicable)
                              │  limit / audit log    │
                              └──────────┬───────────┘
                     ┌───────────────────┼────────────────────┐
                     ▼                   ▼                    ▼
             ┌───────────────┐   ┌───────────────┐    ┌───────────────┐
             │  Agent Core    │   │ Workflow Core  │    │  Domain CRUD   │
             │ (agent loop,   │   │ (DAG engine,   │    │ (providers,    │
             │  subagent      │   │  node runners, │    │  models, mcp,  │
             │  orchestrator) │   │  checkpoints)  │    │  files, ...)   │
             └───────┬───────┘   └───────┬───────┘    └───────┬───────┘
                     │                   │                    │
                     └─────────┬─────────┴──────────┬─────────┘
                                ▼                    ▼
                        ┌───────────────┐   ┌────────────────────┐
                        │  Guardrails    │   │   Task Queue (arq)  │
                        │ (injection,    │   │  Redis-backed;      │
                        │  secret scan,  │   │  worker pool runs   │
                        │  budget, HITL) │   │  long agent/workflow│
                        └───────────────┘   │  jobs durably       │
                                            └──────────┬─────────┘
                                                        ▼
                                              ┌───────────────────┐
                                              │  Sandbox Runner     │
                                              │ (hardened Docker,   │
                                              │  per-language image)│
                                              └───────────────────┘

     Cross-cutting: Postgres (system of record) · Qdrant (RAG, external)
     · OpenTelemetry → Prometheus + Grafana + Loki · Audit log table
```

External MCP services (`rag-service`, `mcp-drive-server`, ...) không đổi vai
trò — vẫn là MCP server độc lập mà backend đăng ký/connect tới, giữ nguyên
pattern hiện tại vì nó đã đúng (loose coupling qua MCP protocol).

---

## 3. Identity, Tenancy & AuthN

### 3.1 Data model mới

| Bảng | Mục đích | Trường chính |
|---|---|---|
| `organization` | Tenant. Mọi resource thuộc về 1 org. | `id, name, slug, created_at` |
| `user` | Tài khoản đăng nhập. | `id, email (unique), hashed_password (nullable nếu chỉ OAuth), display_name, is_active` |
| `membership` | User ↔ Org, mang role. | `org_id, user_id, role, invited_by, created_at` (unique `org_id,user_id`) |
| `oauth_account` | Liên kết social login. | `user_id, provider, provider_account_id, access_token_enc, refresh_token_enc` |
| `refresh_token` | JWT refresh token, revoke được. | `id, user_id, token_hash, expires_at, revoked_at, replaced_by_id, user_agent, ip` |
| `api_key` | Key cho agent-to-agent / CI / script. | `id, org_id, name, key_prefix, key_hash, scopes(json), created_by, last_used_at, revoked_at` |

Tất cả bảng nghiệp vụ hiện có (`Agent, Model, Provider, McpServer, Workflow,
WfNode, WfEdge, Session, Message, UsageEvent, UploadedFile, AgentMemory,
SessionMemory`) thêm cột `org_id` (FK, indexed) + `created_by_user_id`
(nullable, để phân biệt ai tạo trong cùng 1 org).

### 3.2 AuthN

- **Đăng nhập chuẩn**: email + password (argon2id hash) **và** OIDC (Google,
  GitHub tối thiểu) qua `authlib`. Không bắt buộc chọn 1 trong 2 — hỗ trợ cả
  hai, vì "dự án lớn" luôn cần cả login nội bộ lẫn SSO.
- **JWT access token** (15 phút, ký RS256/EdDSA để verify được ở nhiều
  service sau này mà không cần secret dùng chung) + **refresh token** (7–30
  ngày, httponly cookie, rotate mỗi lần dùng, lưu hash trong DB để revoke
  được — chống replay).
- **API key** cho use-case máy-gọi-máy (CI, script, agent gọi agent qua HTTP
  ngoài): định dạng `oa_live_<random>`, chỉ lưu hash, hiển thị full key **một
  lần duy nhất** lúc tạo (như GitHub PAT).
- `verify_api_key` hiện tại (`core/security.py`) được **giữ lại** như một chế
  độ auth bổ sung (machine key), không xoá — nhưng route con người dùng UI đi
  qua JWT.

### 3.3 Middleware / dependency chain

```
Request
  → AuthN dependency: resolve JWT hoặc API key → (user_id | api_key_id), org_id
  → AuthZ dependency: require_permission("resource:action") → check Membership.role
  → Object-ownership check (nếu route thao tác 1 resource cụ thể): resource.org_id == ctx.org_id
  → Audit middleware: log hành động nếu thuộc danh sách "audited actions"
  → Route handler
```

---

## 4. AuthZ / RBAC

### 4.1 Role

4 role ở cấp Organization (giữ đơn giản, đủ dùng, dễ hiểu — không làm ABAC
phức tạp ngay từ đầu):

| Role | Có thể làm |
|---|---|
| `owner` | Tất cả, kể cả xoá org, quản lý billing (sau này), đổi role của người khác kể cả admin |
| `admin` | Quản lý member/role (trừ owner), quản lý provider/model/mcp, xem audit log |
| `developer` | Tạo/sửa/chạy agent, workflow, tool; **không** quản lý member hay provider nhạy cảm (API key của LLM provider) |
| `viewer` | Chỉ đọc: xem agent/workflow/debug/usage, không chạy, không sửa |

### 4.2 Permission matrix

Định nghĩa **tĩnh trong code** (`app/core/authz/policy.py`), không phải bảng
DB động — dễ review, dễ test, đủ linh hoạt cho quy mô dự án này:

```python
PERMISSIONS: dict[Role, set[str]] = {
    Role.owner:     {"*"},
    Role.admin:     {"org:manage_members", "providers:manage", "mcp:manage",
                     "agents:*", "workflows:*", "tools:*", "audit:read", ...},
    Role.developer: {"agents:create", "agents:run", "workflows:create",
                     "workflows:run", "tools:use:safe", "tools:use:read",
                     "tools:use:write", "tools:use:execute", ...},
    Role.viewer:    {"agents:read", "workflows:read", "usage:read"},
}
```

FastAPI dependency `require_permission("workflows:run")` tra bảng này theo
role của user trong org hiện tại. Không có permission → 403, có audit log.

### 4.3 Tool capability gate (fix gap lớn nhất hiện tại)

`ToolSpec` (hiện tại ở `core/tools/types.py`) được mở rộng:

```python
@dataclass
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    run: Callable[..., Awaitable[str]]
    risk_tier: RiskTier            # safe | read | write | execute | network | dangerous
    requires_approval: bool = False
    timeout_s: float = 30.0
    max_retries: int = 0
```

Capability được kiểm 2 lớp, không chỉ 1 như hiện tại:
1. **Agent-level**: tool phải nằm trong `agent.tools` (như cũ).
2. **Org/role-level**: `risk_tier` của tool phải nằm trong tập risk tier mà
   role của người sở hữu/chạy agent được phép (`developer` không tự động được
   `dangerous`, phải org admin bật riêng cho từng agent qua
   `agent.allowed_risk_tiers` hoặc yêu cầu approval).

`run_shell` (hiện không sandbox, tự ghi "DANGEROUS" trong description) được
xếp `risk_tier = dangerous`, `requires_approval = True` mặc định — không xoá
tool nhưng không ai chạy được nó "vô thức" nữa.

---

## 5. Security Guardrails

Module mới `app/core/guardrails/`, tách khỏi RBAC (RBAC = "ai được làm gì",
guardrail = "hành vi runtime có an toàn không"):

| Guardrail | Vị trí gắn vào | Cơ chế |
|---|---|---|
| **Prompt-injection filter** | Trước khi nội dung từ tool (web_fetch, rag_search, file đọc được) được nối vào context | Heuristic pattern list (câu lệnh giả danh "system", link lạ, base64 dài bất thường) + cờ `untrusted_content` gắn kèm block, nhắc model rõ ràng đây là dữ liệu không phải chỉ thị |
| **Secret / PII scanner** | Trước khi lưu message vào DB, trước khi trả kết quả tool ra ngoài | Regex (API key patterns, JWT, AWS keys...) + entropy check trên chuỗi dài; match → redact + audit log |
| **Loop / runaway circuit breaker** | Trong `agent_loop.py`, `workflow/engine.py` | Thay thế config chết `loop_warn/loop_block/loop_circuit` bằng cơ chế thật: đếm tool-call trùng lặp (hash tên+args), cap tổng số tool-call/run, cap cost (USD) tích luỹ/run, cap wall-clock/run — vượt ngưỡng thì dừng cứng, không chỉ "nhắc model" như hiện tại |
| **Resource quota (sandbox)** | `core/tools/sandbox.py` | Giữ + siết: `--network none` mặc định, `--memory`, `--cpus`, `--pids-limit`, `--read-only` rootfs + tmpfs `/work`, `--security-opt no-new-privileges`, seccomp profile mặc định của Docker, timeout wall-clock cứng (kill container), giới hạn output đã có (giữ) |
| **Human-in-the-loop approval** | Bất kỳ tool/node có `requires_approval=True` | Tạo `ApprovalRequest`, agent/workflow **pause**, emit SSE event `approval_required`; UI hiện approval inbox; approve/reject resume run qua queue |
| **Audit log** | Middleware + guardrail triggers | Bảng `audit_log` (immutable, append-only): login, đổi role, tạo/xoá API key, chạy tool `dangerous`, quyết định approval |

---

## 6. Agent Core v2

### 6.1 Sửa lỗi nền tảng trước tiên

`read_attachment`, `write_file`, `list_dir`, `search_files` hiện là `def`
(sync) nhưng bị `await` — 3/5 test đang fail thật. Đây là **việc đầu tiên**
trong plan (M0), độc lập với toàn bộ phần còn lại, không phụ thuộc gì.

### 6.2 Subagent → mô hình `Task` có audit

Thay vì `call_agent` chỉ tăng `ctx.depth` và chạy đệ quy trong cùng process
(hiện tại), mỗi lần subagent được gọi tạo 1 bản ghi `task`:

```
task(id, org_id, parent_task_id, root_run_id, agent_id, goal,
     status[pending|running|succeeded|failed|cancelled],
     result, cost_usd, token_usage_json, started_at, finished_at, depth)
```

→ Debug UI vẽ được **cây delegation** thật (ai gọi ai, tốn bao nhiêu, kết quả
gì) thay vì chỉ thấy 1 message dài. `depth` vẫn giữ giới hạn đệ quy
(`max_agent_depth`) như cơ chế chống loop hiện có.

### 6.3 Orchestrator pattern (tuỳ chọn, bật theo agent)

Thêm `agent.kind: "worker" | "orchestrator"`. Orchestrator agent chạy 1 bước
"decompose" (LLM tự chia goal thành sub-task list có thứ tự/song song), rồi
dispatch từng sub-task như `Task` cho `call_agent` — về bản chất là một
"workflow được sinh động bởi LLM" thay vì vẽ tay. Đây là phần biến hệ thống từ
"agent loop" thành cảm giác thật sự "AgentOS".

### 6.4 Tool registry v2

`risk_tier`, `timeout_s`, `max_retries`, `requires_approval` (mục 4.3) +
validate `args` bằng JSON schema thật (dùng `jsonschema` lib) trước khi gọi
`run`, không chỉ tin schema LLM tự tuân theo.

---

## 7. Workflow Engine v2

Giữ nguyên **điểm mạnh hiện tại** (DAG wavefront scheduler,
`asyncio.gather` fan-out/fan-in) — không viết lại, chỉ bổ sung:

| Bổ sung | Lý do |
|---|---|
| **Durable execution**: `WorkflowRun` + `WorkflowNodeRun` ghi DB mỗi bước | Hiện tại workflow chạy hoàn toàn trong 1 request/process — API restart giữa chừng là mất toàn bộ tiến trình. Ghi checkpoint cho phép resume. |
| **Queued mode**: node `agent`/`tool` được dispatch qua `arq` job thay vì `asyncio.create_task` trực tiếp khi `workflow_execution_mode=queued` | Cho phép chạy song song **vượt qua 1 process** — scale ngang bằng cách thêm worker container, đúng yêu cầu "dễ scale". Chế độ `inline` giữ nguyên cho workflow nhỏ/latency thấp. |
| **Retry/timeout per node** | Node có thể khai `retry: {max_attempts, backoff}`, `timeout_s` — hiện tại lỗi 1 node là node đó fail hẳn, không retry. |
| **Sequential helper** | Thực chất đã làm được bằng cạnh nối tuần tự, nhưng thêm 1 "chain" node-group helper ở tầng UI/schema để không phải vẽ tay khi chỉ cần A→B→C. |
| **Sub-workflow node** | 1 workflow gọi workflow khác như 1 node — composability, tái dùng workflow con. |
| **Approval node** | Node `type=approval` tạo `ApprovalRequest`, pause nhánh đó tới khi được duyệt — tái dùng guardrail ở mục 5. |
| **An toàn `_eval_condition`** | Thay `eval()` trần (dù đã strip builtins) bằng `simpleeval` hoặc AST-whitelist evaluator — không execute code tuỳ ý qua edge condition. |

---

## 8. Observability

| Lớp | Công cụ | Vai trò |
|---|---|---|
| Logging | `structlog`, JSON output, `request_id/run_id/org_id/user_id` bind theo context | Log tra cứu được xuyên suốt 1 request/run |
| Tracing | OpenTelemetry SDK, FastAPI auto-instrument + span thủ công quanh: agent iteration, tool call, workflow node, sandbox exec | Nhìn thấy latency breakdown thật của 1 run |
| Metrics | `prometheus-fastapi-instrumentator` (HTTP) + custom Counter/Histogram: `tool_calls_total`, `tool_call_duration_seconds`, `agent_run_cost_usd`, `workflow_run_duration_seconds`, `sandbox_executions_total`, `queue_depth` | Dashboard + alert |
| Dashboard | Grafana, provisioned JSON trong repo (`observability/grafana/dashboards/*.json`) | Usage/cost theo org, error rate, latency p50/p95, queue backlog |
| Log aggregation | Loki + Promtail (đọc log container) | Tìm log theo `run_id` xuyên nhiều service (api, worker, sandbox) |
| Alerting | Alertmanager rule tối thiểu: error rate spike, budget vượt ngưỡng, queue backlog cao, sandbox failure rate cao | Webhook tới Slack/email (cấu hình sau, hook sẵn) |
| Audit | Bảng `audit_log` riêng (mục 5) | Không lẫn với log vận hành — phục vụ compliance/soi lại sau này |

Toàn bộ stack observability chạy dưới Docker Compose `--profile observability`
— optional, không bắt buộc lúc dev nhẹ.

---

## 9. Data layer & Deployment readiness

- **DB**: chuyển default sang Postgres (`asyncpg`) cho mọi môi trường ngoài
  dev đơn máy; SQLite chỉ còn là "quick local test" mode. Alembic quản lý toàn
  bộ migration mới (org/user/rbac/task/workflow-run/audit/api-key).
- **Queue**: Redis + `arq` (async-native, nhẹ, hợp với codebase asyncio hiện
  tại hơn Celery vốn thiên sync/thread-pool).
- **Docker Compose** (root `docker-compose.yml`, mới — hiện chưa có ở root):
  `frontend, api, worker, postgres, redis, qdrant, rag-service, otel-collector,
  prometheus, grafana, loki, promtail` (observability qua profile riêng).
- **Health checks**: `/healthz` (liveness, không chạm dependency) và
  `/readyz` (check DB + Redis) — dùng cho Compose healthcheck, sẵn sàng làm
  k8s probe sau này không cần đổi code.
- **CI**: GitHub Actions — hiện **chưa tồn tại** (`.github/` rỗng) — thêm
  workflow lint+test backend (ruff + pytest) và frontend (eslint + tsc +
  build) chạy trên mọi PR.
- **12-factor config**: toàn bộ secret qua env/`.env`, không hard-code; ghi rõ
  trong docs upgrade path sang Vault/SOPS là **out of scope v1**, không tự
  làm quá tay.

---

## 10. Những gì cố tình KHÔNG làm (giữ phạm vi hợp lý)

- Không tự viết ABAC/policy engine động (OPA/Cedar) — permission matrix tĩnh
  đủ dùng ở quy mô này, thêm sau nếu thật sự cần.
- Không chuyển sang Kubernetes ngay — thiết kế stateless để **sẵn sàng** lên
  K8s, nhưng không viết Helm chart trong v1 (theo đúng lựa chọn "Docker
  Compose, 1 host" đã chốt).
- Không đổi sang microVM sandbox — Docker hardened đã chốt; nếu sau này có
  nhu cầu chạy code không tin cậy từ nhiều tenant lạ, đây là điểm quay lại.
- Không làm billing/subscription — Organization model chừa chỗ (`plan`
  field) nhưng không implement billing logic.
