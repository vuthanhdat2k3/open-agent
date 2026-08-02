# M13 — Flight Recorder (OTel GenAI + audit runtime đầy đủ)

## Branch

`agentos-v2/m13-flight-recorder` từ `main`.

## Depends on

M7 (observability). M13 **nâng cấp** phần M7 đã làm, không viết lại từ đầu.

## Goal

Mọi hành động của agent trở nên truy vết được theo **chuẩn ngành**, và bất
biến ở mức audit. Một dữ liệu phục vụ 3 mục đích: debug, sinh eval case
(M15), bằng chứng tuân thủ EU AI Act Điều 12.

## Scope

**Trong phạm vi**: đổi attribute span sang OTel GenAI semantic conventions,
thêm span LLM riêng có token/model, mở rộng audit runtime, gắn
`agent_release_id` vào trace + audit, wire nốt metric đã định nghĩa mà chưa
dùng.

**Ngoài phạm vi**: lấy mẫu trace thành eval case (đó là M15), export sang
SIEM (M17), thay đổi hạ tầng collector (đã có ở M8).

## Bối cảnh: M7 đã làm gì (ĐỌC TRƯỚC KHI CODE)

Không làm lại những thứ này, chỉ sửa/mở rộng:

| Vị trí | Đã có |
|---|---|
| `agent_loop.py:298` | span `agent_loop.iteration`, attrs `org_id`, `agent_id`, `depth` |
| `agent_loop.py:402` | span `tool.call`, attrs `org_id`, `agent_id`, `tool_name`, `risk_tier` |
| `agent_loop.py:412` | counter `tool_calls_total{name,status}` |
| `agent_loop.py:414` | `log_action` **chỉ cho** `risk_tier=dangerous` |
| `agent_loop.py:426-428` | `wrap_untrusted_if_flagged` + `scan_and_redact` — chạy nhưng **không audit** |
| `agent_loop.py:543` | counter `agent_run_cost_usd_total{org_id}` |
| `agent_loop.py:181` | `agent_release_id` **đã có sẵn** trong `ToolContext` — chỉ cần dùng |
| `workflow/engine.py:279` | span quanh node run |
| `metrics.py:11` | `tool_call_duration_seconds` **định nghĩa rồi nhưng chưa dùng ở đâu** |

## Chuẩn tham chiếu

OpenTelemetry GenAI semantic conventions. Convention còn đang tiến hoá —
**kiểm tra lại spec tại thời điểm implement**, ưu tiên bản stable nhất trong
`opentelemetry-semantic-conventions` đang pin. Attribute cần dùng:

```
gen_ai.operation.name        # "chat" | "execute_tool" | "invoke_agent"
gen_ai.system                # "openai" | "anthropic" | ... (từ provider.key)
gen_ai.request.model
gen_ai.response.model
gen_ai.request.temperature
gen_ai.usage.input_tokens
gen_ai.usage.output_tokens
gen_ai.response.finish_reasons
gen_ai.tool.name
gen_ai.tool.call.id
gen_ai.agent.id
gen_ai.agent.name
gen_ai.conversation.id       # = session_id
```

Quy ước tên span: `{gen_ai.operation.name} {model}` — ví dụ `chat gpt-4o-mini`,
`execute_tool web_fetch`, `invoke_agent researcher`.

Attribute nội bộ **không thuộc chuẩn** (`org_id`, `agent_release_id`,
`risk_tier`) giữ nguyên ý nghĩa cũ nhưng thêm prefix `openagent.` để phân
biệt rõ với attr chuẩn: `openagent.org_id`, `openagent.agent_release_id`,
`openagent.risk_tier`.

## Files to add

- `backend/app/core/observability/genai.py` — helper tập trung:
  - `llm_span(provider, model, temperature, session_id, agent)` context manager
  - `tool_span(spec, call_id, agent)` context manager
  - `record_usage(span, usage, model_row)` — set token attrs + metric
  - `set_common(span, agent, ctx)` — set `openagent.*` + `gen_ai.agent.*`
  - Mục đích: **một chỗ duy nhất biết tên attribute**, đổi convention chỉ sửa 1 file.
- `backend/tests/test_genai_conventions.py`
- `backend/tests/test_audit_runtime.py`
- `backend/alembic/versions/00XX_add_audit_log_indexes.py` — index
  `(org_id, created_at)` và `(org_id, action)` trên `audit_logs` (bảng này
  sắp tăng volume mạnh; query cho M15/M17 sẽ lọc theo 2 cột này).

## Files to modify

- `backend/app/core/observability/metrics.py`
  - Thêm `gen_ai_client_token_usage` (Histogram, labels: `org_id`,
    `model`, `token_type` ∈ {input, output}).
  - Thêm `gen_ai_client_operation_duration` (Histogram, labels: `org_id`,
    `operation`, `model`).
  - Thêm `guardrail_events_total` (Counter, labels: `org_id`, `kind` ∈
    {injection_flagged, secret_redacted, approval_required, budget_exceeded},
    `outcome`).
- `backend/app/core/llm.py`
  - `stream()` phải trả usage khi kết thúc (OpenAI-compatible: bật
    `stream_options={"include_usage": True}`). Nếu provider không hỗ trợ,
    fallback = 0 và set attr `openagent.usage_estimated=true` — **không được
    im lặng bỏ qua**.
- `backend/app/core/agent_loop.py`
  - Đổi span `agent_loop.iteration` → `invoke_agent {agent.name}` với
    `gen_ai.operation.name=invoke_agent`, `gen_ai.agent.id`,
    `gen_ai.agent.name`, `gen_ai.conversation.id`, `openagent.org_id`,
    `openagent.agent_release_id` (lấy từ `agent.active_release_id`,
    đã có sẵn ở dòng 181), `openagent.depth`.
  - **Thêm span mới** `chat {model}` bọc riêng lời gọi `llm.stream(...)` —
    hiện tại không có span nào giữ model/token. Set
    `gen_ai.request.model/temperature`, và khi stream xong set
    `gen_ai.usage.input_tokens/output_tokens`,
    `gen_ai.response.finish_reasons`.
  - Đổi span `tool.call` → `execute_tool {name}` với `gen_ai.tool.name`,
    `gen_ai.tool.call.id`, `openagent.risk_tier`.
  - Wire `tool_call_duration_seconds` quanh `execute_tool_call` (metric đã
    tồn tại, chưa dùng).
  - Mở rộng audit: `log_action` cho **mọi** tool call, không chỉ `dangerous`.
    Dùng `action="tool.executed"`, `metadata={"risk_tier":..., "status":...}`.
    Giữ nguyên `tool.dangerous.executed` cho tier dangerous (backward compat
    với alert/dashboard hiện có).
  - Audit guardrail tại dòng 426-428: khi `wrap_untrusted_if_flagged` thực sự
    bọc → `action="guardrail.injection_flagged"`; khi `scan_and_redact` trả
    `secret_findings` không rỗng → `action="guardrail.secret_redacted"` với
    `metadata={"count": len(findings), "types": [...]}` — **không log giá trị
    secret**.
- `backend/app/core/workflow/engine.py`
  - Span node run theo cùng convention: `invoke_agent`/`execute_tool` tuỳ
    node type, thêm `openagent.workflow_run_id`, `openagent.node_id`.
- `backend/app/core/guardrails/approval.py`, `budget.py`
  - `log_action` + `guardrail_events_total` khi chặn/yêu cầu duyệt.
- `backend/app/core/quota/*`
  - `log_action` khi từ chối do quota (`action="quota.denied"`).
- `backend/pyproject.toml`
  - Pin `opentelemetry-semantic-conventions` tường minh (đang là dependency
    gián tiếp) để đổi convention không xảy ra ngầm khi rebuild.
- `backend/app/config.py`
  - `otel_capture_message_content: bool = False` — bật/tắt việc ghi nội dung
    prompt/completion vào span event. **Mặc định tắt** (nội dung có thể chứa
    PII; convention cũng coi đây là opt-in).

## Quyết định thiết kế cần tuân thủ

1. **Audit không được làm hỏng run.** `log_action` hiện `await db.commit()`
   bên trong. Gọi nó trên mọi tool call sẽ commit rất nhiều lần giữa vòng
   lặp. Xử lý: thêm tham số `commit: bool = True`, các call site trong
   `agent_loop` truyền `commit=False` và để transaction ngoài commit một
   lần — **hoặc** đẩy audit qua queue. Chọn cách 1 trước (đơn giản hơn,
   không thêm hạ tầng); nếu benchmark cho thấy nghẽn thì mới chuyển queue.
2. **Không log nội dung nhạy cảm.** Audit metadata chỉ chứa thống kê
   (số lượng, loại, tên tool), không chứa nội dung tool result hay secret.
   Nội dung prompt/completion chỉ vào span event khi
   `otel_capture_message_content=True`.
3. **Cardinality metric.** Không đưa `session_id`/`agent_id` làm label
   Prometheus (unbounded). Chỉ `org_id`, `model`, `tool_name`, `status`.
4. **Tương thích ngược.** Giữ counter/metric cũ đang có dashboard M7 trỏ
   tới. Chỉ *thêm*, không đổi tên metric đã tồn tại.

## Step-by-step

1. `genai.py` trước — thuần helper, test độc lập được, chưa đụng luồng chạy.
2. Wire `genai.py` vào `agent_loop.py`: span `invoke_agent` (đổi tên +
   attrs), rồi thêm span `chat` mới. Chạy test tracing in-memory exporter
   xác nhận cây span cha-con đúng: `invoke_agent → chat`, `invoke_agent →
   execute_tool`.
3. Sửa `llm.py` để stream trả usage; xác nhận `gen_ai.usage.*` xuất hiện
   trên span `chat`.
4. Thêm tham số `commit` cho `log_action`, rồi mở rộng audit trong
   `agent_loop` (tool call + guardrail).
5. Audit cho approval/budget/quota.
6. Workflow engine theo cùng convention.
7. Metric mới + wire `tool_call_duration_seconds`.
8. Migration index cho `audit_logs`.
9. Cập nhật `observability/grafana/dashboards/*` để dùng metric mới (không
   xoá panel cũ).

## Suggested commit breakdown

1. `feat(agentos-m13): genai semantic-convention helper module`
2. `refactor(agentos-m13): agent_loop spans follow otel genai conventions`
3. `feat(agentos-m13): dedicated chat span with model + token usage`
4. `feat(agentos-m13): llm stream returns usage (include_usage)`
5. `refactor(agentos-m13): log_action supports deferred commit`
6. `feat(agentos-m13): audit every tool call + guardrail decision`
7. `feat(agentos-m13): audit approval/budget/quota denials`
8. `refactor(agentos-m13): workflow engine spans follow genai conventions`
9. `feat(agentos-m13): genai token/duration/guardrail metrics`
10. `perf(agentos-m13): index audit_logs on (org_id, created_at) and (org_id, action)`
11. `test(agentos-m13): genai convention + runtime audit tests`

## Tests to write

`test_genai_conventions.py` (dùng `InMemorySpanExporter` như M7 đã làm):

- Chạy 1 agent loop ngắn với fake LLM → assert tồn tại span tên
  `invoke_agent <name>` và span con `chat <model>`.
- Span `chat` có đủ: `gen_ai.operation.name == "chat"`,
  `gen_ai.request.model`, `gen_ai.usage.input_tokens`,
  `gen_ai.usage.output_tokens` (> 0 với fake usage).
- Tool call sinh span `execute_tool <tool>` có `gen_ai.tool.name` và
  `openagent.risk_tier`.
- Mọi span đều có `openagent.org_id` và `openagent.agent_release_id`.
- `otel_capture_message_content=False` (mặc định) → **không** có event chứa
  nội dung prompt; bật lên thì có.

`test_audit_runtime.py`:

- 1 tool call thường → 1 row `action="tool.executed"`.
- 1 tool `dangerous` → có **cả** `tool.executed` và `tool.dangerous.executed`
  (không phá dashboard cũ).
- Tool result chứa pattern secret → 1 row `guardrail.secret_redacted`, và
  `metadata` **không chứa** giá trị secret (assert tường minh).
- Tool result chứa prompt injection → 1 row `guardrail.injection_flagged`.
- Quota từ chối → 1 row `quota.denied`.
- Cross-tenant: audit row luôn có đúng `org_id` của agent, không rò sang org khác.

Regression:

- Toàn bộ `pytest` cũ xanh — đặc biệt `test_audit_log.py` (M7) không được vỡ.

## CI additions

- Không cần service container mới.
- Thêm bước assert convention không bị drift: test kiểm tra danh sách
  attribute mà `genai.py` phát ra khớp với hằng số import từ
  `opentelemetry.semconv` (bắt được khi nâng version làm đổi tên attr).

## PR checklist

```
- [ ] genai.py là chỗ DUY NHẤT hardcode tên attribute gen_ai.*
- [ ] Span cây: invoke_agent → chat, invoke_agent → execute_tool (test in-memory exporter)
- [ ] Span chat có gen_ai.request.model + gen_ai.usage.input_tokens/output_tokens thật (không phải 0 giả)
- [ ] Mọi span có openagent.org_id + openagent.agent_release_id
- [ ] Nội dung prompt/completion chỉ ghi khi otel_capture_message_content=True (mặc định False)
- [ ] Audit ghi: mọi tool call, injection flagged, secret redacted, approval, budget, quota denied
- [ ] Audit metadata KHÔNG chứa giá trị secret / nội dung tool result (có test assert)
- [ ] log_action không commit giữa vòng lặp agent (commit=False + commit ngoài)
- [ ] Metric mới không dùng label unbounded (không có session_id/agent_id làm label)
- [ ] Metric/dashboard M7 cũ vẫn hoạt động, không đổi tên
- [ ] Migration index audit_logs chạy được cả upgrade lẫn downgrade
- [ ] pytest xanh, CI xanh
```