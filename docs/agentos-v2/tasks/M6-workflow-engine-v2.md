# M6 — Workflow Engine v2 (Durable execution + queue)

## Branch
`agentos-v2/m6-workflow-engine-v2` từ `main` (sau khi M4 **và** M5 đã merge
— cần `ApprovalRequest` từ M4 cho node approval, cần `Task` từ M5 cho node
agent ghi nhận đúng subagent).

Khối lượng lớn — khuyến nghị chẻ: `agentos-v2/m6-01-durable-state` (model +
persistence, chưa đổi execution mode) → `agentos-v2/m6-02-queue-worker` (arq
+ queued mode) → `agentos-v2/m6-03-node-types` (approval/sub_workflow/retry/
timeout).

## Scope
**Trong phạm vi**: `WorkflowRun`/`WorkflowNodeRun` persistence, chế độ
`queued` qua Redis+arq, node type mới (`approval`, `sub_workflow`), retry/
timeout per node.
**Ngoài phạm vi**: không đổi thuật toán wavefront scheduler hiện có
(`is_ready`, `active_edges`) — chỉ bọc thêm persistence + queue xung quanh.

## Depends on
M4 (approval node), M5 (agent node ghi Task đúng).

## Files to add
- `backend/app/models/workflow_run.py`
- `backend/app/models/workflow_node_run.py`
- `backend/alembic/versions/00XX_add_workflow_run_tables.py`
- `backend/app/worker.py` (arq worker entry point)
- `backend/app/core/workflow/jobs.py` (arq job definitions:
  `run_workflow_node`)
- `backend/app/core/workflow/queue.py` (arq pool client wrapper)
- `backend/tests/test_workflow_durable_execution.py`
- `backend/tests/test_workflow_queue_resume.py` (cần Redis thật hoặc
  `fakeredis` — quyết định dựa trên CI runner có Redis service container
  hay không, xem phần CI additions)

## Files to modify
- `backend/pyproject.toml` — thêm `arq`, `redis`.
- `backend/app/config.py` — thêm `redis_url`, `workflow_execution_mode:
  Literal["inline","queued"] = "inline"`.
- `backend/app/core/workflow/engine.py`:
  - Sau mỗi node hoàn thành/lỗi (trong `run_node`, dòng ~53-113 theo báo cáo
    review trước), ghi 1 `WorkflowNodeRun` row (status, input, output,
    error, timestamps) — **không đổi** logic `is_ready`/`active_edges`.
  - Thêm nhánh: nếu `settings.workflow_execution_mode == "queued"`, thay
    `asyncio.create_task(run_node(...))` bằng
    `queue.enqueue_job("run_workflow_node", workflow_run_id, node_id)`.
  - Thêm xử lý node `type="approval"` (dùng `guardrails.approval` từ M4).
  - Thêm xử lý node `type="sub_workflow"`: đọc `node.config["workflow_id"]`,
    gọi đệ quy `WorkflowEngine(...).run(child_workflow_id, node_input)`.
  - Thêm field đọc từ node config: `retry={max_attempts, backoff_s}`,
    `timeout_s` — wrap việc chạy node bằng `asyncio.wait_for` +
    retry loop với backoff.
- `backend/app/services/workflow_service.py` — thêm hàm tạo `WorkflowRun`
  khi bắt đầu 1 lần chạy, trả `workflow_run_id` cho route/SSE dùng.
- `backend/app/api/v1/routes/workflows.py` — route chạy workflow trả kèm
  `workflow_run_id`; thêm `GET /workflows/runs/{id}` (trạng thái + danh sách
  node run) cho frontend polling/hiển thị.
- Root `docker-compose.yml` — nếu M8 chưa làm, tạo file tối thiểu ở đây với
  service `redis` + `worker` để test queued mode local (M8 sẽ hoàn thiện đầy
  đủ sau).

## Step-by-step
1. Thêm persistence trước (không đổi execution mode) — an toàn nhất, dễ
   test riêng: mỗi lần node complete/fail, ghi `WorkflowNodeRun`. Chạy toàn
   bộ test workflow hiện có để chắc chắn không phá hành vi cũ.
2. Thêm `arq` worker skeleton (`worker.py`, `jobs.py`) — job
   `run_workflow_node` đọc `WorkflowRun`/`WorkflowNodeRun` state từ DB (không
   nhận state qua argument job để đảm bảo durable — nếu worker chết giữa
   chừng, job mới đọc lại đúng state từ DB).
3. Thêm nhánh `queued` trong engine — giữ `inline` là default, `queued` opt-in
   qua config, để không phá hành vi mặc định của milestone trước.
4. Viết test "kill worker giữa chừng": chạy 1 job, kill process worker (hoặc
   mock để job 1 raise rồi dừng), khởi động worker mới, xác nhận node đã
   `succeeded` không chạy lại, chỉ node còn `pending`/`ready` được enqueue
   tiếp.
5. Thêm node type `approval`, `sub_workflow`, retry/timeout — mỗi loại 1
   test riêng.

## Suggested commit breakdown
1. `feat(agentos-m6): workflow_run + workflow_node_run models + migration`
2. `feat(agentos-m6): persist node run state in workflow engine (inline mode unchanged)`
3. `feat(agentos-m6): arq worker skeleton + run_workflow_node job`
4. `feat(agentos-m6): queued execution mode for workflow engine`
5. `feat(agentos-m6): approval node type in workflow engine`
6. `feat(agentos-m6): sub_workflow node type`
7. `feat(agentos-m6): per-node retry + timeout config`
8. `feat(agentos-m6): GET /workflows/runs/{id} status endpoint`
9. `test(agentos-m6): durable execution + worker-restart resume tests`

## Tests to write
- `test_workflow_durable_execution.py`: chạy workflow 5 node (2 song song →
  merge → agent → output) ở `inline` mode → assert `WorkflowNodeRun` ghi đủ 5
  dòng đúng thứ tự thời gian hợp lý (node song song có `started_at` gần
  nhau).
- `test_workflow_queue_resume.py`: chạy ở `queued` mode, giữa chừng "kill"
  worker (dừng consumer loop), assert job pending vẫn còn trong Redis queue,
  khởi động worker mới, assert workflow hoàn thành đúng, không node nào chạy
  2 lần (kiểm bằng đếm số `WorkflowNodeRun` row mỗi `node_id` = 1, trừ node
  có retry thật sự).
- Test node `approval`: workflow có node approval giữa đường → status
  `waiting_approval`, sau khi `POST /approvals/{id}/decide approved` →
  workflow tiếp tục đúng nhánh.
- Test node `sub_workflow`: workflow cha gọi workflow con → output workflow
  con trở thành input node kế tiếp của workflow cha.
- Test retry: node cấu hình `retry.max_attempts=3` với tool luôn fail 2 lần
  đầu rồi pass lần 3 → node cuối cùng `status="succeeded"`, có 3
  `WorkflowNodeRun` (hoặc 1 row với `attempt` tăng dần — quyết định lúc
  implement, ghi rõ trong code comment nếu chọn 1 row/attempt thay vì nhiều
  row).

## CI additions
Thêm Redis service container vào job `backend` trong `.github/workflows/ci.yml`:
```yaml
services:
  redis:
    image: redis:7
    ports: ["6379:6379"]
```
Set `REDIS_URL=redis://localhost:6379/0` trong `env:` của job cho các test
cần Redis thật (`test_workflow_queue_resume.py`).

## PR checklist
```
- [ ] WorkflowNodeRun ghi đúng cho cả node chạy song song và tuần tự, inline mode không đổi hành vi cũ
- [ ] Chế độ queued hoạt động qua Redis+arq, kill/restart worker giữa chừng không chạy lại node đã xong
- [ ] Node approval pause/resume đúng qua ApprovalRequest (M4)
- [ ] Node sub_workflow chạy workflow con đúng, output truyền đúng sang node cha
- [ ] Retry/timeout per node hoạt động, có test
- [ ] CI có Redis service container, test liên quan Redis pass trong CI thật (không chỉ local)
- [ ] pytest xanh, CI xanh
```
