# Handoff — tiếp tục AgentOS v2 từ M14

> Copy toàn bộ file này làm prompt cho Codex. Viết ngày 2026-08-02.

---

## Bối cảnh

Bạn tiếp quản repo `open-agent` (OpenAgent — multi-agent OS, monorepo:
`backend/` FastAPI, `frontend/` Next.js 15, `rag-service/` RAG microservice
qua MCP, `mcp-drive-server/`).

Roadmap đang theo: `docs/agentos-v2/ROADMAP_2026.md` (M13–M17), mỗi
milestone có file đặc tả riêng trong `docs/agentos-v2/tasks/`.

**M0–M12 đã xong từ trước. M13 và M14 vừa hoàn thành.** Việc của bạn là
M15 → M16 → M17, cộng vài mục tồn đọng liệt kê bên dưới.

### ĐỌC TRƯỚC KHI VIẾT BẤT KỲ DÒNG CODE NÀO

1. `docs/agentos-v2/ROADMAP_2026.md` — vì sao lộ trình xếp như vậy.
2. `docs/agentos-v2/IMPLEMENTATION_PLAN.md` — **mục "Git Workflow & PR
   Policy"**, áp dụng bắt buộc, không ngoại lệ.
3. `docs/agentos-v2/tasks/M15-closed-eval-loop.md` — task kế tiếp.
4. `backend/app/core/observability/genai.py` và
   `backend/app/core/workflow/replay.py` — hai module M13/M14 vừa thêm, bạn
   sẽ dùng lại chứ không viết lại.

---

## Trạng thái hiện tại

### Nhánh

```
main
└── docs/roadmap-2026                       (docs M13–M17)
    └── agentos-v2/m13-flight-recorder       (8 commits, XONG)
        └── agentos-v2/m14-durable-execution (4 commits, XONG) ← HEAD
```

Cả ba nhánh **chưa merge và chưa mở PR**. Việc đầu tiên của bạn là mở PR
theo thứ tự `docs/roadmap-2026` → `m13` → `m14`, dùng đúng PR checklist
trong file task tương ứng.

### M13 — Flight Recorder (xong)

| Commit | Nội dung |
|---|---|
| `0a00a39` | `app/core/observability/genai.py` — nơi DUY NHẤT biết tên attribute `gen_ai.*`, lấy hằng số từ `opentelemetry.semconv` |
| `48f5645` | `llm.stream()` trả token thật qua `stream_options.include_usage`, kèm cờ `estimated` khi provider không báo |
| `196c856` | Span theo chuẩn: `invoke_agent` → `chat` / `execute_tool` (cha-con thật, trước đây là sibling phẳng) |
| `c77e2c6` | Audit MỌI tool call + quyết định guardrail; `log_action(commit=False)` để không commit mỗi tool call |
| `be37599` | Audit approval / budget / risk-tier denial / 4 điểm quota rejection |
| `623fd6b` | Workflow engine span theo cùng convention |
| `86f0b8c` | Migration `0016` — index `audit_logs` trên `(org_id, created_at)` và `(org_id, action)` |
| `64695ca` | `tests/test_genai_conventions.py` (9 test) + `tests/test_audit_runtime.py` (6 test) |

### M14 — Durable execution (xong)

| Commit | Nội dung |
|---|---|
| `1f28b06` | Model `ToolCallRecord` + cột lease/resume trên `workflow_runs` + migration `0017` |
| `ab3df41` | `app/core/workflow/resume.py` — resume không chạy lại node đã succeeded, lease chống chạy trùng, `MAX_RESUME_ATTEMPTS` |
| `c6d7535` | `app/core/workflow/replay.py` — replay tất định, `ReplayDiverged` khi lệch nhánh |
| `294a2d3` | `sweep_orphans` chạy lúc worker khởi động |

Test: `tests/test_workflow_resume.py` (7), `tests/test_workflow_replay.py` (9).

### Trạng thái test (baseline — QUAN TRỌNG)

```
3 failed, 76 passed, 39 errors
```

**39 error và 3 failure là có sẵn, KHÔNG phải do M13/M14.** Nguyên nhân:
test cố kết nối Postgres từ xa (`OPENAGENT_DB_URL` trỏ Supabase), máy dev
không có DB local chạy → `InterfaceError` / `Event loop is closed`.

Trước khi bạn sửa gì, hãy chạy `pytest` một lần để lấy baseline của máy
bạn. **Chỉ so số với baseline đó**, đừng cho rằng mọi thứ phải xanh hết.
Nếu bạn dựng được Postgres local (`docker compose up postgres`) thì phần
lớn 39 error sẽ biến mất — nên làm, và nếu làm được thì báo lại số mới.

---

## Việc tồn đọng (làm trước M15)

Đây là những thứ đặc tả M13/M14 có nêu nhưng chưa làm. Đều nhỏ.

1. **Grafana dashboard chưa dùng metric mới.** M13 thêm
   `gen_ai_client_token_usage`, `gen_ai_operation_duration_seconds`,
   `guardrail_events_total` nhưng
   `observability/grafana/dashboards/*.json` chưa có panel nào cho chúng.
   Thêm panel mới, **không xoá panel cũ** (metric M7 vẫn còn nguyên).

2. **API endpoint replay chưa có.** `replay.py` đã sẵn sàng nhưng chưa có
   route. Đặc tả M14 yêu cầu
   `POST /api/workflows/runs/{id}/replay` → tạo run mới với
   `replay_of_run_id`. Cột `replay_of_run_id` đã có trong DB, chưa ai ghi.

3. **`extend_lease` chưa có ai gọi.** Hàm đã viết và test nhưng chưa có
   heartbeat trong lúc chạy. Node chạy lâu hơn `DEFAULT_LEASE_SECONDS`
   (300s) sẽ bị worker khác cướp run. Cần gọi định kỳ trong
   `run_workflow_events`, hoặc nâng TTL nếu bạn thấy đơn giản hơn — **nêu
   rõ lựa chọn trong PR**.

4. **Replay mới nối vào agent loop, chưa nối vào workflow engine.**
   `_agent_stream` nhận `replay_cursor`, nhưng `engine.py` chưa truyền
   xuống. Workflow replay end-to-end vì thế chưa chạy được.

---

## Nhiệm vụ chính

Theo đúng thứ tự, mỗi milestone một nhánh riêng, mỗi nhánh một PR:

### M15 — Khép vòng trace → eval → cổng chặn (3–4 tuần)

Đặc tả đầy đủ: `docs/agentos-v2/tasks/M15-closed-eval-loop.md`.

Đây là **điểm khác biệt thật** của sản phẩm — chưa nền tảng mã nguồn mở nào
khép trọn vòng này. Ba phần: sampler lấy trace production thành eval case,
grader chuyên cho retrieval (recall@k / MRR / groundedness), cổng chặn
publish + auto-rollback.

Ba ràng buộc **không được vi phạm**:

- Case lấy mẫu **luôn phải có người duyệt** trước khi vào dataset. Máy
  không biết đáp án đúng là gì. Sampler đề xuất, con người quyết định.
- Grader phải **tất định**, chạy được trong CI **không cần credential
  provider**. Không đưa LLM-as-a-judge vào đường chạy bắt buộc.
- Auto-rollback **mặc định TẮT**, có cooldown, có audit khi kích hoạt. Tự
  động đổi release production là hành vi mạnh, phải chủ động bật.

### M16 — Liên thông A2A + danh tính agent (4–6 tuần)

Đặc tả: `docs/agentos-v2/tasks/M16-a2a-agent-identity.md`.

**Đọc lại spec A2A chính thức tại thời điểm bạn làm** — spec còn tiến hoá,
đừng code theo mô tả trong file task như thể nó là spec.

Bất biến quan trọng nhất: **quyền hiệu lực = giao của quyền user và quyền
agent identity**. Agent không bao giờ có quyền cao hơn người gọi nó. Phải
có test riêng cho điều này.

### M17 — Mở khoá mua hàng doanh nghiệp

Đặc tả: `docs/agentos-v2/tasks/M17-enterprise-unlock.md`.

**KHÔNG bắt đầu khi chưa có khách hàng cụ thể yêu cầu.** Đây là milestone
duy nhất có điều kiện khởi động. SAML/SCIM xây sớm = code chết phải bảo
trì. Ngoại lệ: phần 17D (bộ nhớ phân tầng nóng/ấm/lạnh) có lợi ích kỹ
thuật độc lập, có thể tách ra làm sớm nếu muốn.

---

## Quy ước bắt buộc

### Git

- Nhánh: `agentos-v2/m<n>-<slug>`, tạo từ nhánh milestone trước.
- Commit: Conventional Commits, scope `agentos-m<n>`.
  Ví dụ: `feat(agentos-m15): trace sampler proposes cases from audit signals`
- Chia commit theo mục "Suggested commit breakdown" trong file task.
- PR description dùng đúng "PR checklist" của file task, tick từng dòng.
- **Không commit thẳng vào `main`.**

### Code

- **Tenant isolation trước tiên**: mọi bảng mới có `org_id`, mọi query
  scope theo tenant. Phải có test cross-tenant.
- **Chuẩn trước, tự chế sau**: có semantic convention / RFC đã chín thì
  theo chuẩn. `genai.py` là ví dụ — lấy hằng số từ `opentelemetry.semconv`
  chứ không hardcode chuỗi.
- **Không log dữ liệu nhạy cảm**: audit metadata chỉ chứa thống kê (số
  lượng, loại, tên tool), không chứa nội dung tool result hay secret. Mọi
  thứ đi vào chỗ lưu trữ lâu dài phải qua `scan_and_redact`.
- **Tương thích ngược**: chỉ *thêm* metric, không đổi tên metric cũ (M7
  dashboard đang trỏ vào).
- **Fail có chủ đích**: không nuốt lỗi im lặng. Ví dụ tham chiếu:
  `ReplayDiverged` dừng hẳn thay vì âm thầm gọi tool thật;
  `usage_estimated=True` đánh dấu số ước lượng để không ai nhầm là số đo.
- Đánh dấu chỗ đơn giản hoá có trần rõ ràng bằng comment `# ponytail:` nêu
  trần và hướng nâng cấp. Ví dụ có sẵn trong `models/workflow_run.py`.

### Test

- Mỗi logic không tầm thường để lại ít nhất một test chạy được.
- Test cả **điều KHÔNG được xảy ra**, không chỉ happy path. Ví dụ tham
  chiếu: `test_recorded_result_is_redacted` khẳng định secret **không** có
  trong bản ghi; `test_replay_returns_recorded_output_without_executing`
  đếm số lần thực thi để chứng minh replay **không** gọi tool.
- Migration phải test được cả `upgrade` lẫn `downgrade`.
  Lưu ý: chain migration từ đầu trên SQLite trắng **bị lỗi có sẵn** (0001
  giả định `agent_memories` tồn tại). Cách test đã dùng: tạo schema từ
  `Base.metadata.create_all`, đưa schema về trạng thái revision trước, rồi
  `alembic stamp <rev-1>` và `alembic upgrade head`.

### Lint / CI

- `ruff check .` phải sạch (CI chỉ chạy cái này).
- **Không chạy `ruff format`** trên toàn repo: 46 file hiện chưa
  format-clean và CI không enforce, reformat sẽ tạo diff rác che mất thay
  đổi thật.

---

## Cạm bẫy đã gặp

- `log_action` mặc định `commit=True`. Trong vòng lặp agent phải truyền
  `commit=False` rồi flush một lần mỗi iteration, nếu không sẽ có một round
  trip DB cho mỗi tool call.
- `Model.display_name` là NOT NULL — fixture test phải set.
- Đừng đặt FK tự tham chiếu trên SQLite (đã bỏ FK của
  `replay_of_run_id` vì nó chặn `DROP COLUMN`).
- `agent.active_release_id` đã có sẵn trong `ToolContext`
  (`agent_loop.py:181`) — dùng lại, đừng query lại.
- Trong test, closure của fake LLM stream giữ state qua nhiều lần chạy —
  phải tạo generator mới cho mỗi run, nếu không lần thứ hai sẽ không phát
  sinh tool call.
- Docker Desktop có thể không chạy trên máy dev → test cần Docker
  (`test_run_shell_echo`) sẽ fail. Là môi trường, không phải code.

---

## Cách bắt đầu

```bash
git checkout agentos-v2/m14-durable-execution
cd backend && .venv/Scripts/python -m pytest tests/ -q   # lấy baseline
```

Rồi đọc `docs/agentos-v2/tasks/M15-closed-eval-loop.md` và bắt đầu từ mục
"Suggested commit breakdown" số 1.

Nếu bạn thấy đặc tả nào sai so với code thật, **sửa đặc tả và nói rõ trong
PR** — đừng code theo đặc tả sai. Đã có tiền lệ: bản roadmap đầu tiên viết
"runtime hoàn toàn im lặng", đọc code mới thấy M7 đã instrument một phần,
và đặc tả M13 được sửa lại trước khi code.
