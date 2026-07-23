# M4 — Security Guardrails

## Branch
`agentos-v2/m4-guardrails` từ `main` (sau khi M3 merge).

## Scope
**Trong phạm vi**: prompt-injection filter, secret/PII scanner, budget
circuit breaker thật (thay circuit breaker "chỉ nhắc model" hiện tại), human
approval flow (`ApprovalRequest`), thay `eval()` trần trong workflow
condition bằng evaluator an toàn, siết thêm Docker flags cho sandbox.
**Ngoài phạm vi**: durable/queued workflow execution (M6) — approval node
trong workflow engine ở M4 chỉ cần pause đúng, chưa cần chạy qua queue.

## Depends on
M3 (cần `risk_tier`/`requires_approval` đã có trên `ToolSpec`, cần
`org_id`/user context từ M1-M2 để gắn vào `ApprovalRequest`/`AuditLog`).

## Files to add
- `backend/app/core/guardrails/__init__.py`
- `backend/app/core/guardrails/injection.py`
- `backend/app/core/guardrails/secrets.py`
- `backend/app/core/guardrails/budget.py`
- `backend/app/core/guardrails/approval.py`
- `backend/app/models/approval_request.py`
- `backend/app/api/v1/routes/approvals.py`
- `backend/alembic/versions/00XX_add_approval_request.py`
- `backend/tests/test_guardrails_injection.py`
- `backend/tests/test_guardrails_secrets.py`
- `backend/tests/test_guardrails_budget.py`
- `backend/tests/test_approval_flow.py`

## Files to modify
- `backend/pyproject.toml` — thêm `simpleeval`.
- `backend/app/core/agent_loop.py`:
  - Sau tool `web_fetch`/`rag_search` (MCP)/`read_attachment` trả về, gọi
    `injection.flag_untrusted(result)` trước khi append vào history.
  - Trước `session_repo.persist(...)`, gọi `secrets.scan_and_redact(...)`
    trên nội dung message.
  - Thay đoạn circuit-breaker hiện tại (`_is_tool_failure`, dòng ~275-317)
    bằng `BudgetTracker` — giữ logic "inject fix message" cho lỗi thường,
    thêm nhánh dừng cứng khi `BudgetTracker.exceeded()`.
  - Khi tool có `requires_approval=True`: gọi
    `approval.request_approval(...)`, `yield` SSE event `approval_required`,
    dừng loop tại đó (không raise, không tiếp tục) — resume xử lý ở route
    `POST /approvals/{id}/decide`.
- `backend/app/core/workflow/engine.py`:
  - Thay `_eval_condition` (dòng ~16-20, dùng `eval()`) bằng
    `simpleeval.simple_eval` với whitelist operator.
  - Thêm `BudgetTracker` riêng theo mỗi `WorkflowRun` (khởi tạo lúc engine
    bắt đầu chạy).
  - Thêm xử lý node `type="approval"`: gọi `request_approval`, đặt
    node status `waiting_approval`, không cho downstream chạy tới khi
    resolve.
- `backend/app/core/tools/sandbox.py` — thêm flag Docker:
  `--security-opt no-new-privileges`, `--pids-limit=64`, `--read-only`,
  `--tmpfs /work:rw,size=64m` vào lệnh `docker run` hiện có (giữ
  `--network none` mặc định).
- `backend/app/config.py` — thêm `budget_max_tool_calls=40`,
  `budget_max_cost_usd=2.0`, `budget_max_wall_seconds=300`,
  `budget_max_repeated_call=3` (đây là cơ chế thật thay cho
  `loop_warn/block/circuit` đã xoá ở M0).

## Step-by-step
1. Viết `injection.py`, `secrets.py` như 2 module thuần hàm (input string →
   output string/flag), test độc lập trước khi wiring — dễ TDD.
2. Viết `budget.py`: `BudgetTracker` dataclass với method `record_call(name,
   args, cost)`, `exceeded() -> str | None` (trả lý do nếu vượt ngưỡng nào).
3. Viết `ApprovalRequest` model + migration + `approval.py`
   (`request_approval`, `resolve_approval`, `get_pending`).
4. Route `approvals.py`: `GET /approvals` (list theo org, permission
   `approvals:read`), `POST /approvals/{id}/decide` (permission
   `approvals:decide`, mặc định chỉ `admin`/`owner` — kiểm tra trong
   `PERMISSIONS` matrix từ M3, thêm entry nếu chưa có).
5. Wiring vào `agent_loop.py` — đây là phần rủi ro nhất (đụng vòng lặp
   chính), viết test trước khi sửa: mock 1 agent gọi lặp lại 1 tool y hệt >
   `budget_max_repeated_call` lần → assert loop dừng với lý do rõ ràng.
6. Wiring vào `workflow/engine.py` tương tự.
7. Thay `eval()` bằng `simpleeval`, chạy lại toàn bộ test workflow hiện có để
   đảm bảo condition cũ (nếu test nào dùng) vẫn evaluate đúng.
8. Siết Docker flags trong sandbox, chạy `test_sandbox_rejects_traversal`
   (đã fix ở M0) + test resource-limit mới.

## Suggested commit breakdown
1. `feat(agentos-m4): prompt-injection heuristic filter`
2. `feat(agentos-m4): secret/PII scanner + redaction`
3. `feat(agentos-m4): real budget circuit breaker (tool-call/cost/wall-time/repeat caps)`
4. `feat(agentos-m4): approval_request model + request/resolve helpers`
5. `feat(agentos-m4): approvals API routes`
6. `refactor(agentos-m4): wire guardrails into agent_loop`
7. `refactor(agentos-m4): wire budget tracker + approval node into workflow engine`
8. `fix(agentos-m4): replace bare eval() with simpleeval in workflow condition`
9. `fix(agentos-m4): harden sandbox docker flags (no-new-privileges, pids-limit, read-only rootfs)`
10. `test(agentos-m4): guardrails + approval flow tests`

## Tests to write
- `test_guardrails_injection.py`: input chứa chuỗi kiểu "ignore previous
  instructions" từ nguồn web_fetch → output bị bọc marker
  `<untrusted_content>`, không bị model hiểu nhầm là chỉ thị hệ thống (test
  ở mức unit, chỉ kiểm tra output string, không cần gọi LLM thật).
- `test_guardrails_secrets.py`: chuỗi chứa `AKIA...` (AWS key giả) và JWT giả
  → bị redact, không xuất hiện trong output.
- `test_guardrails_budget.py`: `BudgetTracker` với `max_repeated_call=3`,
  gọi tool y hệt 4 lần → `exceeded()` trả lý do ở lần thứ 4.
- `test_approval_flow.py`: agent với tool `dangerous` (`run_shell`) →
  `ApprovalRequest` được tạo, agent loop dừng đúng chỗ; `POST decide
  approved` → resume và tool chạy; `POST decide rejected` → run kết thúc với
  lỗi rõ ràng, không tool nào chạy.
- Test riêng cho `simpleeval` thay `eval()`: condition hợp lệ evaluate đúng,
  condition cố tình độc hại (`__import__('os')...`) bị reject an toàn thay vì
  execute.

## CI additions
Không cần job mới. Đảm bảo test approval flow không cần Docker thật chạy
trong CI (mock `subprocess`/docker call trong `test_guardrails_budget.py` và
test liên quan sandbox nếu CI runner không có Docker sẵn — kiểm tra
`ci.yml` job `backend` có Docker daemon hay không trước khi viết test gọi
Docker thật).

## PR checklist
```
- [ ] Injection filter bọc đúng nội dung untrusted từ web_fetch/rag_search/read_attachment
- [ ] Secret scanner redact được ít nhất AWS key pattern + JWT pattern, có test
- [ ] BudgetTracker dừng cứng khi vượt max_tool_calls/max_cost_usd/max_wall_seconds/max_repeated_call
- [ ] ApprovalRequest tạo đúng khi tool requires_approval=True, agent loop pause đúng chỗ
- [ ] POST /approvals/{id}/decide approve/reject hoạt động, resume hoặc kết thúc run đúng
- [ ] eval() trần trong workflow engine đã thay bằng simpleeval, test chặn được payload độc hại
- [ ] Docker sandbox có no-new-privileges/pids-limit/read-only rootfs
- [ ] pytest xanh, CI xanh
```
