# M14 — Durable Execution & Time-Travel Replay

## Branch

`agentos-v2/m14-durable-execution` từ `main` (sau khi M13 merge).

## Depends on

- **M13** — span/audit theo chuẩn là nguồn dữ liệu để đối chiếu khi replay.
- **M6** — workflow engine v2 + queue (arq) đã có sẵn.

## Goal

Workflow chạy nhiều giờ sống sót qua restart/crash của worker, và mọi run
đều replay lại được y hệt để debug hành vi bất định mà không tốn tiền gọi
LLM thật.

## Bối cảnh: đã có sẵn gì

Đọc trước, đừng thiết kế lại:

- `workflow_run`: `org_id`, `workflow_id`, `status`, `input`, `output`,
  `error`, `started_at`, `finished_at`, `triggered_by_user_id`.
- `workflow_node_run`: `workflow_run_id`, `node_id`, `agent_release_id`,
  `status`, `attempt`, `input`, `output`, `error`, `started_at`,
  `finished_at`.

**Quan trọng**: `workflow_node_run.output` **đã chính là checkpoint** ở mức
node. M14 không cần thêm bảng checkpoint mới cho workflow — chỉ cần logic
biết dùng nó. Phần thiếu thật sự là (a) resume, (b) cache tool output cho
replay ở mức agent loop, (c) khoá chống chạy trùng.

## Scope

**Trong phạm vi**: resume workflow từ node dở dang, cache tool output +
replay tất định, chống chạy trùng khi nhiều worker cùng nhận 1 run.

**Ngoài phạm vi**: fork/branch một run thành nhánh mới (chỉ replay tuyến
tính), multi-region, canary.

## Data model

Bảng mới duy nhất:

- `ToolCallRecord` — cache output tool để replay.
  - `id`, `org_id`
  - `workflow_run_id` (nullable — agent chat không có workflow)
  - `session_id` (nullable)
  - `node_run_id` (nullable)
  - `sequence: int` — thứ tự gọi tool trong 1 run, dùng để replay đúng thứ tự
  - `tool_name`, `arguments_hash` (sha256 của JSON args đã chuẩn hoá key),
    `arguments` (JSON), `result` (Text), `status`, `duration_ms`
  - `created_at`
  - Unique: `(workflow_run_id, node_run_id, sequence)`
  - Index: `(org_id, session_id)`, `(org_id, workflow_run_id)`

Cột thêm vào bảng có sẵn:

- `workflow_run.resume_count: int = 0` — đếm số lần đã resume, để alert khi
  một run resume quá nhiều (dấu hiệu crash loop).
- `workflow_run.lease_owner: str | None`, `workflow_run.lease_expires_at:
  datetime | None` — khoá chống 2 worker cùng chạy 1 run.
- `workflow_run.replay_of_run_id: str | None` — nếu run này là bản replay
  của run khác.

## Thiết kế

### 1. Resume

- Khi worker khởi động: quét `workflow_run` có `status="running"` và
  (`lease_expires_at IS NULL` hoặc `lease_expires_at < now()`) →
  đây là run mồ côi do worker chết.
- Resume = chạy lại engine với cùng `workflow_run_id`, nhưng engine phải
  **bỏ qua** mọi node có `workflow_node_run.status="succeeded"` và nạp
  `output` của chúng vào state thay vì chạy lại.
- Node đang `running` khi crash → coi là thất bại, tăng `attempt`, chạy lại
  từ đầu node đó (không có checkpoint trong lòng node — chấp nhận, node là
  đơn vị nguyên tử nhỏ nhất).
- Tăng `resume_count`; nếu vượt ngưỡng (đề xuất 3) → chuyển `status="failed"`
  với error rõ ràng thay vì lặp vô hạn.

### 2. Lease (chống chạy trùng)

- Trước khi chạy, worker `UPDATE workflow_run SET lease_owner=:wid,
  lease_expires_at=now()+interval WHERE id=:id AND (lease_expires_at IS NULL
  OR lease_expires_at < now())` — chỉ worker nào update được 1 row mới chạy.
- Worker gia hạn lease định kỳ (heartbeat) trong khi chạy.
- Đây là **optimistic lock ở tầng DB**, không cần thêm hạ tầng.
  `# ponytail: DB-level lease, chuyển sang Redis lock nếu contention cao`

### 3. Replay

- Chế độ `replay_of_run_id` được set → mọi lời gọi tool **không thực thi
  thật** mà đọc `ToolCallRecord` của run gốc theo `(node_run_id, sequence)`.
- Nếu replay yêu cầu một tool call không có trong bản ghi gốc (vì LLM đi
  nhánh khác) → dừng replay, đánh dấu `status="diverged"` và báo rõ điểm
  rẽ nhánh. **Không được im lặng gọi tool thật** — đó là bẫy tốn tiền và
  gây side effect ngoài ý muốn.
- Replay dùng lại `agent_release_id` đã lưu trên `workflow_node_run` để
  đảm bảo đúng cấu hình gốc.

## Files to add

- `backend/app/models/tool_call_record.py`
- `backend/alembic/versions/00XX_durable_execution.py`
- `backend/app/core/workflow/resume.py` — quét run mồ côi, lease, resume
- `backend/app/core/workflow/replay.py` — replay executor
- `backend/tests/test_workflow_resume.py`
- `backend/tests/test_workflow_replay.py`

## Files to modify

- `backend/app/core/workflow/engine.py` — bỏ qua node đã `succeeded`, ghi
  `ToolCallRecord`, tôn trọng chế độ replay.
- `backend/app/core/agent_loop.py` — ghi `ToolCallRecord` cho mỗi tool call;
  ở chế độ replay thì đọc thay vì gọi.
- `backend/app/worker.py` — hook khởi động chạy `resume.sweep_orphans()`;
  task heartbeat gia hạn lease.
- `backend/app/api/v1/routes/workflows.py` — `POST
  /api/workflows/runs/{id}/replay` trả về run mới có `replay_of_run_id`.
- `backend/app/services/workflow_service.py` — nghiệp vụ replay, scope theo org.
- `backend/app/core/observability/metrics.py` — `workflow_resumes_total`,
  `workflow_replay_diverged_total`.

## Suggested commit breakdown

1. `feat(agentos-m14): tool_call_record model + migration`
2. `feat(agentos-m14): workflow_run lease columns + optimistic lock`
3. `feat(agentos-m14): engine skips succeeded nodes on resume`
4. `feat(agentos-m14): orphan run sweep on worker startup`
5. `feat(agentos-m14): record tool calls in agent_loop and engine`
6. `feat(agentos-m14): deterministic replay executor`
7. `feat(agentos-m14): replay API endpoint`
8. `feat(agentos-m14): resume/replay metrics`
9. `test(agentos-m14): resume + replay tests`

## Tests to write

`test_workflow_resume.py`:

- Chạy workflow 3 node, kill giữa node 2 → resume → node 1 **không** chạy
  lại (assert `attempt` của node 1 vẫn = 1), node 2 chạy lại, node 3 chạy.
- 2 worker cùng nhận 1 run → chỉ 1 chạy được (lease), worker kia bỏ qua.
- `resume_count` vượt ngưỡng → run chuyển `failed`, không lặp vô hạn.
- Lease hết hạn → worker khác nhặt được.

`test_workflow_replay.py`:

- Replay một run đã xong với fake LLM trả cùng tool call → kết quả giống
  hệt, và **không** tool nào được thực thi thật (assert bằng spy).
- Replay mà LLM đòi tool không có trong bản ghi → `status="diverged"`, có
  thông tin điểm rẽ nhánh, không gọi tool thật.
- Replay dùng đúng `agent_release_id` của run gốc.
- Cross-tenant: không replay được run của org khác.

## CI additions

Không cần service mới (test dùng SQLite in-memory + fake executor như M11).

## PR checklist

```
- [ ] Resume KHÔNG chạy lại node đã succeeded (có test assert attempt không tăng)
- [ ] Lease ngăn 2 worker chạy trùng 1 run (có test)
- [ ] resume_count có ngưỡng, không crash loop vô hạn
- [ ] Replay KHÔNG bao giờ gọi tool thật — kể cả khi thiếu bản ghi (assert bằng spy)
- [ ] Replay lệch nhánh -> status="diverged" với thông tin rõ, không im lặng
- [ ] ToolCallRecord không lưu secret thô (đi qua scan_and_redact như M13)
- [ ] Mọi query scope theo org_id
- [ ] Migration up/down chạy được
- [ ] pytest xanh, CI xanh
```