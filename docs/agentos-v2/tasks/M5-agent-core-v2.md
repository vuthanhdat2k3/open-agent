# M5 — Agent Core v2 (Subagent Task model + Orchestrator + Tool registry v2)

## Branch
`agentos-v2/m5-agent-core-v2` từ `main` (sau khi M3 merge — **không** cần
đợi M4, 2 milestone này độc lập, có thể làm song song bởi 2 người/agent khác
nhau miễn cả hai đều rebase lên M3).

## Scope
**Trong phạm vi**: model `Task` (subagent delegation có audit), sửa
`call_agent` để ghi `Task`, `Agent.kind` (worker/orchestrator), validate
JSON schema args trước khi chạy tool, debug API trả cây delegation.
**Ngoài phạm vi**: chạy subagent qua queue (đó là liên quan M6 — M5 vẫn chạy
subagent in-process như hiện tại, chỉ thêm audit trail).

## Depends on
M3 (risk tier cần có để `Task` audit ghi được, và vì `call_agent` bản thân
cũng là 1 tool cần qua capability gate).

## Files to add
- `backend/app/models/task.py`
- `backend/alembic/versions/00XX_add_task_table.py`
- `backend/tests/test_task_delegation.py`
- `backend/tests/test_tool_schema_validation.py`

## Files to modify
- `backend/app/core/tools/builtins.py` — sửa `call_agent`/`_call_agent`
  (dòng khoảng 111-130 theo báo cáo review trước): trước khi chạy subagent
  loop, tạo `Task(status="pending", parent_task_id=ctx hiện tại nếu có,
  root_run_id, agent_id, goal, depth)`; set `status="running"`; sau khi
  chạy xong set `status="succeeded"/"failed"`, `result`, `cost_usd`,
  `token_usage`, `finished_at`. Giữ nguyên logic depth-gate
  (`ctx.depth >= settings.max_agent_depth`) không đổi.
- `backend/app/core/tools/types.py` (`ToolContext`) — thêm field
  `current_task_id: str | None = None`, `root_run_id: str | None = None` để
  truyền xuống các lệnh `call_agent` lồng nhau.
- `backend/app/models/agent.py` — thêm cột
  `kind: Mapped[str] = mapped_column(default="worker")`
  (`Literal["worker","orchestrator"]`, validate ở schema Pydantic, không
  cần DB enum cứng).
- `backend/app/services/agent_service.py` — khi `kind="orchestrator"`, nối
  thêm đoạn system prompt cố định (hằng số
  `ORCHESTRATOR_SYSTEM_SUFFIX` trong `core/agent_loop.py` hoặc
  `core/prompts.py` mới) hướng dẫn model: "bạn có thể gọi call_agent nhiều
  lần, tuần tự hoặc để nhiều tool_call trong 1 lượt để chạy song song, để
  hoàn thành các phần việc con của mục tiêu chính".
- `backend/app/core/tools/registry.py` / nơi build tool schema cho LLM —
  thêm bước `jsonschema.validate(args, spec.input_schema)` ngay sau khi parse
  args từ LLM tool-call, trước khi gọi `spec.run(...)`; bắt
  `jsonschema.ValidationError` → trả `tool_result` dạng
  `error: invalid arguments: <message>` thay vì để tool tự nhận args sai và
  lỗi khó hiểu.
- `backend/app/api/v1/routes/debug.py` — thêm
  `GET /debug/tasks/{root_run_id}` trả cây `Task` (parent→children, dùng
  CTE recursive hoặc load hết theo `root_run_id` rồi build tree ở Python vì
  số lượng nhỏ, không cần recursive SQL phức tạp).
- `backend/app/schemas/agent.py` — thêm `kind` vào request/response schema.
- `backend/pyproject.toml` — thêm `jsonschema`.

## Step-by-step
1. Viết `Task` model + migration trước, độc lập.
2. Sửa `ToolContext` thêm 2 field mới — vì `dataclass`, đây là thay đổi
   backward-compatible (có default), không phá code khác đang tạo
   `ToolContext(...)`.
3. Sửa `call_agent`: bọc logic hiện tại bằng try/finally để đảm bảo `Task`
   luôn được update status kể cả khi subagent raise exception.
4. Thêm `jsonschema.validate` vào điểm gọi tool chung (tìm đúng 1 chỗ dùng
   chung cho cả `agent_loop.py` và `workflow/engine.py` — có thể là 1 hàm
   helper `execute_tool_call(spec, args, ctx)` mới trong
   `core/tools/registry.py` để 2 nơi gọi cùng logic, tránh duplicate).
5. Thêm `kind` cho Agent, orchestrator prompt suffix.
6. Viết `GET /debug/tasks/{root_run_id}`.
7. Test: dựng 1 agent A (orchestrator) gọi `call_agent` tới B 2 lần (giả lập
   bằng cách mock LLM response trả 2 tool_call `call_agent` trong 1 lượt) →
   assert `Task` tree đúng 3 node.

## Suggested commit breakdown
1. `feat(agentos-m5): add task model for subagent delegation audit`
2. `feat(agentos-m5): extend ToolContext with task/run tracking fields`
3. `feat(agentos-m5): wire task creation/status into call_agent tool`
4. `feat(agentos-m5): shared execute_tool_call helper with jsonschema arg validation`
5. `feat(agentos-m5): add agent.kind (worker/orchestrator) + orchestrator system prompt`
6. `feat(agentos-m5): debug endpoint for task delegation tree`
7. `test(agentos-m5): subagent delegation + tool schema validation tests`

## Tests to write
- `test_task_delegation.py`: mock LLM để agent A gọi `call_agent` tới B rồi
  C (tuần tự) → assert 3 `Task` row, đúng `parent_task_id`, đúng
  `root_run_id`, `status="succeeded"` sau khi xong; test case subagent raise
  exception → `Task.status="failed"`, không để row treo ở `running` mãi.
- `test_task_delegation.py::test_depth_limit_still_enforced` — đảm bảo thêm
  Task tracking không vô tình phá depth-gate hiện có.
- `test_tool_schema_validation.py`: gọi tool với args thiếu field bắt buộc
  trong `input_schema` → trả `error: invalid arguments`, không raise
  exception không kiểm soát lên trên.
- `test_debug_tasks_endpoint.py`: seed 1 cây Task 3 node → `GET
  /debug/tasks/{root_run_id}` trả đúng cấu trúc cha-con.

## CI additions
Không cần job mới; đảm bảo `jsonschema` được cài trong bước
`pip install -e ".[dev]"` (thêm vào `pyproject.toml` `dependencies`, không
phải chỉ `dev`).

## PR checklist
```
- [ ] Task model ghi đúng parent/root/status/cost mỗi lần call_agent chạy
- [ ] Task status không bao giờ treo ở "running" khi subagent lỗi (try/finally đúng)
- [ ] depth-gate (max_agent_depth) vẫn hoạt động như cũ, có test xác nhận
- [ ] jsonschema validate args trước khi chạy tool, cả agent_loop lẫn workflow engine dùng chung 1 helper
- [ ] Agent.kind=orchestrator có system prompt phù hợp, test ít nhất 1 kịch bản gọi 2 subagent
- [ ] GET /debug/tasks/{root_run_id} trả đúng cây delegation
- [ ] pytest xanh, CI xanh
```
