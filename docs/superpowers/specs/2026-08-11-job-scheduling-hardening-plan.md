# Plan: Hardening scheduler/worker cho Customer Intelligence (đợt 1)

> Dựa trên: `docs/superpowers/specs/2026-08-11-job-scheduling-hardening-design.md`  
> Cập nhật quan trọng so với spec: mục 7 (case RETRYING research vs delivery) đã được chốt bằng cách đọc code thật — kết quả khác với giả định ban đầu trong spec. Xem "Phát hiện từ code" bên dưới trước khi đọc phần thực thi.

## 0. Phát hiện từ code (thay đổi giả định của spec)

Đọc `workflow.py` + `delivery.py` + `repositories/customer_intelligence.py` cho kết quả khác với spec ban đầu:

1. **`RETRYING` hiện tại chỉ có một nguồn thật:** `EXECUTING → RETRYING` trong `delivery.py:272`, xảy ra khi `run_delivery()` throw sau khi approval đã được approve. Route transition `RESEARCHING → RETRYING` được khai báo trong `CASE_TRANSITIONS` (`repositories/customer_intelligence.py:26`) nhưng **không có caller nào dùng nó** — đây là dead transition.
2. **Gap có sẵn (bug, không phải thiết kế cố ý):** khi `run_research()` raise `ResearchError` hoặc exception khác, case bị bỏ lại ở `RESEARCHING` vĩnh viễn. Route `/cases/{id}/research` (`customer_intelligence.py`) chỉ catch `ResearchError` để trả HTTP 400 — không transition case sang trạng thái retry-able nào. Case đó sẽ không bao giờ xuất hiện lại trong bất kỳ danh sách xử lý nào.
3. **`run_research` chạy inline trong HTTP request, không qua ARQ queue.** `CustomerIntelligenceService.research_case()` gọi trực tiếp, được route gọi trực tiếp. Không có job nào tự động research case `INGESTED` — người dùng (hoặc script) phải tự gọi `POST /cases/{id}/research`.

**Kết luận cho thiết kế đợt 1:**

- `_process_due_retries` (retry tự động) **chỉ cần xử lý một nhánh**: case ở `RETRYING` → gọi lại `run_delivery()` qua approval đã approved. Không cần rẽ nhánh "research hay delivery".
- Phải sửa gap #2 trong cùng đợt này: bọc `run_research()` bằng try/except tại nơi gọi, transition case sang `RETRYING` khi lỗi (thay vì để treo ở `RESEARCHING`). Đây không phải mở rộng scope — không sửa thì cơ chế retry tự động ở đợt 1 không có tác dụng với lỗi research (phần lớn lỗi thực tế: web/company/calendar provider timeout).
- Việc research chạy inline trong HTTP request nằm ngoài phạm vi đợt 1 (chuyển sang job queue là thay đổi kiến trúc lớn hơn, không phải "hardening" — ghi vào backlog).

## 1. Phạm vi đợt 1 (chốt lại theo phát hiện trên)

Trong phạm vi:

1. Bảng `job_schedule_executions` + `JobScheduleExecutionRepository` + `run_leased_tick` — generic, dùng ngay cho `_ci_scheduler_tick`.
2. Cột `retry_count`/`next_retry_at`/`last_retry_triggered_by` trên `ci_cases`.
3. Sửa gap #2: `run_research()` lỗi → case chuyển `RETRYING` với `next_retry_at` tính theo backoff, thay vì treo ở `RESEARCHING`.
4. Job tự động `ci_retry_due_cases` — xử lý case `RETRYING`, luôn gọi lại theo đúng bước đã lỗi:
   - nếu case có `BriefingReport` (đã qua research) → nghĩa là lỗi delivery → gọi lại `run_delivery()` qua approval đã approved.
   - nếu case chưa có `BriefingReport` → nghĩa là lỗi research → gọi lại `run_research()`.
   - (Đây là cách phân biệt đáng tin cậy hơn dựa trên `workflow_run_id`, vì mọi case vào `RESEARCHING` đều set `workflow_run_id` ngay từ đầu — dùng sự tồn tại của `BriefingReport` chính xác hơn.)
5. Endpoint `POST /cases/{id}/retry` — manual retry, API-only, ghi audit phân biệt auto/manual.
6. Docker Compose healthcheck/restart cho `worker`.
7. Metrics tối thiểu.
8. Migration Alembic `0028`.

Ngoài phạm vi đợt 1 (backlog, ghi rõ để không quên):

- Chuyển `run_research()` từ inline HTTP sang ARQ job (thay đổi kiến trúc, không phải hardening).
- Wire `_auto_rollback_sweep`, `_fail_orphaned_chat_runs` vào `run_leased_tick` (đợt 2).
- Cleanup `job_schedule_executions` theo retention.
- UI operations.
- `job_schedule_missed_total` (thuật toán chưa chốt — bỏ khỏi đợt 1, chỉ giữ 3 metric còn lại).

## 2. Thứ tự thực thi

Chia thành 7 bước nhỏ, mỗi bước là một đơn vị có thể review/rollback độc lập. Chạy `pytest -q` sau mỗi bước trước khi qua bước tiếp.

### Bước 1 — Model + migration

**File thay đổi:**
- `backend/app/models/customer_intelligence.py` — thêm class `JobScheduleExecution`; thêm 3 cột vào `ResearchCase`.
- `backend/app/models/__init__.py` — export `JobScheduleExecution` (theo pattern export hiện có).
- `backend/alembic/versions/0028_job_scheduling_hardening.py` — migration mới, `down_revision = "0027_approval_owning_task"`.

**Nội dung migration (additive only):**

```python
def upgrade() -> None:
    op.create_table(
        "job_schedule_executions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("job_key", sa.String(length=64), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(), nullable=False),
        sa.Column("lease_owner", sa.String(length=64), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="running"),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("result_summary", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("job_key", "scheduled_for", name="uq_job_schedule_key_time"),
    )
    op.create_index("ix_job_schedule_executions_job_key", "job_schedule_executions", ["job_key"])
    op.create_index("ix_job_schedule_executions_status", "job_schedule_executions", ["status"])

    op.add_column("ci_cases", sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("ci_cases", sa.Column("next_retry_at", sa.DateTime(), nullable=True))
    op.add_column("ci_cases", sa.Column("last_retry_triggered_by", sa.String(length=36), nullable=True))
    with op.batch_alter_table("ci_cases") as batch_op:
        batch_op.create_foreign_key(
            "fk_ci_cases_last_retry_triggered_by", "users", ["last_retry_triggered_by"], ["id"],
            ondelete="SET NULL",
        )

def downgrade() -> None:
    with op.batch_alter_table("ci_cases") as batch_op:
        batch_op.drop_constraint("fk_ci_cases_last_retry_triggered_by", type_="foreignkey")
    op.drop_column("ci_cases", "last_retry_triggered_by")
    op.drop_column("ci_cases", "next_retry_at")
    op.drop_column("ci_cases", "retry_count")
    op.drop_index("ix_job_schedule_executions_status", table_name="job_schedule_executions")
    op.drop_index("ix_job_schedule_executions_job_key", table_name="job_schedule_executions")
    op.drop_table("job_schedule_executions")
```

Dùng `batch_alter_table` cho FK trên `ci_cases` theo đúng convention migration `0023` (đã dùng batch mode cho `ci_cases`).

**Verify:** `alembic upgrade head` và `alembic downgrade -1` chạy sạch trên SQLite test DB; `alembic upgrade head` lại lần 2 không lỗi.

### Bước 2 — `JobScheduleExecutionRepository` + `run_leased_tick`

**File mới:**
- `backend/app/repositories/job_schedule.py` — `JobScheduleExecutionRepository`.
- `backend/app/core/scheduling/__init__.py`
- `backend/app/core/scheduling/job_keys.py` — constant `JobKey`.
- `backend/app/core/scheduling/tick.py` — `run_leased_tick()`.

```python
# app/core/scheduling/tick.py
from __future__ import annotations
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.base import utc_now
from app.repositories.job_schedule import JobScheduleExecutionRepository

logger = structlog.get_logger(__name__)

def _round_down_to_interval(now: datetime, interval_seconds: int) -> datetime:
    epoch_seconds = int(now.timestamp())
    floored = epoch_seconds - (epoch_seconds % interval_seconds)
    return datetime.utcfromtimestamp(floored)

async def run_leased_tick(
    db: AsyncSession,
    *,
    job_key: str,
    interval_seconds: int,
    lease_seconds: int,
    worker_id: str,
    run: Callable[[], Awaitable[dict]],
) -> None:
    scheduled_for = _round_down_to_interval(utc_now(), interval_seconds)
    repo = JobScheduleExecutionRepository(db)
    execution = await repo.try_claim(
        job_key=job_key, scheduled_for=scheduled_for, lease_owner=worker_id, lease_seconds=lease_seconds,
    )
    if execution is None:
        await logger.adebug("job_tick_skipped_lease_held", job_key=job_key, scheduled_for=scheduled_for.isoformat())
        return
    try:
        result = await run()
    except Exception as exc:  # noqa: BLE001 - lỗi job không được crash worker.
        await repo.mark_failed(execution, error=str(exc))
        await logger.aerror("job_tick_failed", job_key=job_key, error=str(exc))
        return
    await repo.mark_succeeded(execution, result_summary=result or {})
```

**Test:** `backend/tests/test_job_schedule_lease.py` theo mục 11 của spec (2 lời gọi cùng `scheduled_for` → 1 thành công; `scheduled_for` khác → cả 2 thành công; `mark_succeeded`/`mark_failed` đúng field).

### Bước 3 — Backoff policy

**File mới:** `backend/app/core/scheduling/backoff.py`

```python
from __future__ import annotations
import random

MAX_RETRY_COUNT = 5

def compute_backoff_seconds(retry_count: int, *, base: int = 60, cap: int = 3600) -> float:
    """Exponential backoff + full jitter: random(0, min(cap, base * 2^retry_count))."""
    ceiling = min(cap, base * (2 ** retry_count))
    return random.uniform(0, ceiling)
```

**Test:** `backend/tests/test_backoff.py` — `retry_count=0` nằm trong `[0, base]`; `retry_count` lớn bị `cap` chặn; giá trị luôn `>= 0`.

### Bước 4 — Sửa gap #2 (research lỗi phải transition RETRYING) + `ResearchCaseRepository` mới

**File thay đổi:**
- `backend/app/repositories/customer_intelligence.py` — thêm `schedule_retry()`, `list_due_for_retry()` vào `ResearchCaseRepository`.
- `backend/app/customer_intelligence/workflow.py` — **không đổi logic research**, chỉ đảm bảo `ResearchError`/exception khác được xử lý ở lớp gọi (bước tiếp theo), không tự transition trong `workflow.py` (giữ nguyên separation of concerns: `workflow.py` chỉ biết research, không biết về retry policy).
- `backend/app/services/customer_intelligence_service.py` — `research_case()` bọc try/except quanh `run_research()`:

```python
async def research_case(self, *, org_id: str, case_id: str, actor_user_id: str | None = None) -> dict[str, Any]:
    from app.customer_intelligence.workflow import ResearchError, run_research
    from app.core.scheduling.backoff import MAX_RETRY_COUNT, compute_backoff_seconds
    from app.repositories.customer_intelligence import ResearchCaseRepository
    from datetime import timedelta

    try:
        return await run_research(self.db, org_id=org_id, case_id=case_id, actor_user_id=actor_user_id)
    except ResearchError:
        raise  # lỗi "case not found"/"case is not researchable" — không phải lỗi tạm thời, không retry.
    except Exception as exc:  # noqa: BLE001 - lỗi tạm thời (provider/DB) -> retry có backoff.
        case_repo = ResearchCaseRepository(self.db)
        case = await case_repo.get(org_id, case_id)
        if case is not None and case.status == "RESEARCHING":
            next_count = case.retry_count + 1
            if next_count > MAX_RETRY_COUNT:
                await case_repo.transition(case, "DEAD_LETTER")
            else:
                delay = compute_backoff_seconds(case.retry_count)
                await case_repo.schedule_retry(
                    case, next_retry_at=utc_now() + timedelta(seconds=delay), triggered_by=None,
                )
        raise
```

**Quan trọng:** cần thêm `RESEARCHING → DEAD_LETTER` vào `CASE_TRANSITIONS` (hiện chỉ có `RESEARCHING → {REPORT_READY, RETRYING}`), vì case vượt `MAX_RETRY_COUNT` ngay từ vòng research đầu (retry_count đã cao từ trước) cần đường thoát trực tiếp. Xác nhận: cần sửa dict `CASE_TRANSITIONS` trong `repositories/customer_intelligence.py`.

**Test:** `backend/tests/test_ci_research_retry.py` — mock `run_research` raise exception → case chuyển `RETRYING`, `retry_count` tăng, `next_retry_at` được set; `ResearchError` (case not found) → không transition, exception propagate nguyên vẹn.

### Bước 5 — Job tự động `ci_retry_due_cases`

**File thay đổi:** `backend/app/customer_intelligence/scheduler.py` — thêm hàm mới (đặt cùng module scheduler vì cùng domain CI, không tạo module riêng):

```python
async def process_due_retries(db: AsyncSession, *, max_cases: int = 50) -> dict[str, Any]:
    """Xử lý case RETRYING đến hạn: gọi lại đúng bước đã lỗi.

    Phân biệt research vs delivery bằng sự tồn tại của BriefingReport — case
    đã có report nghĩa là lỗi xảy ra ở bước delivery (sau REPORT_READY), case
    chưa có report nghĩa là lỗi ở bước research.
    """
    from app.customer_intelligence.delivery import decide_case_approval  # lazy import, tránh cycle
    from app.customer_intelligence.workflow import run_research
    from app.repositories.customer_intelligence import BriefingReportRepository, ResearchCaseRepository

    case_repo = ResearchCaseRepository(db)
    report_repo = BriefingReportRepository(db)
    cases = await case_repo.list_due_for_retry(utc_now(), limit=max_cases)

    retried = 0
    dead_lettered = 0
    for case in cases:
        report = await report_repo.latest_by_case(case.org_id, case.id)
        try:
            if report is not None:
                # Lỗi ở bước delivery: case đang RETRYING sau EXECUTING thất bại.
                # Approval đã approved từ trước — chạy lại qua đường case-level,
                # không qua decide_case_approval (đã quyết định rồi). Cần helper
                # mới trong delivery.py để resume EXECUTING mà không yêu cầu
                # một quyết định approval mới. Xem "Điểm cần review kỹ" dưới đây.
                await case_repo.transition(case, "EXECUTING")
                # ... gọi lại run_delivery với approval đã có, xem ghi chú dưới
            else:
                await case_repo.transition(case, "RESEARCHING")
                await run_research(db, org_id=case.org_id, case_id=case.id, actor_user_id=None)
            retried += 1
        except Exception as exc:  # noqa: BLE001
            from app.core.scheduling.backoff import MAX_RETRY_COUNT, compute_backoff_seconds
            if case.retry_count + 1 > MAX_RETRY_COUNT:
                await case_repo.transition(case, "DEAD_LETTER")
                dead_lettered += 1
            else:
                delay = compute_backoff_seconds(case.retry_count)
                await case_repo.schedule_retry(case, next_retry_at=utc_now() + timedelta(seconds=delay), triggered_by=None)
    return {"due": len(cases), "retried": retried, "dead_lettered": dead_lettered}
```

**Điểm cần review kỹ trước khi code thật (không tự quyết ở bước plan):** nhánh delivery retry cần gọi lại `run_delivery()` với `approval` đã `approved` — nhưng `run_delivery()` hiện được gọi từ `decide_case_approval()` ngay sau khi set `decision`, không có API độc lập "chạy lại delivery cho một approval đã approved từ trước". Cần đọc lại `decide_case_approval()` để quyết định: (a) trích xuất `run_delivery()` call thành hàm resume riêng có thể gọi độc lập, hay (b) query lại `ApprovalRequest` đã `approved` gần nhất cho case rồi gọi `run_delivery()` trực tiếp (bỏ qua `decide_case_approval` vì decision đã có). Hướng (b) đơn giản hơn và không đổi `delivery.py` — ưu tiên hướng này, nhưng cần xác nhận `run_delivery()` không có side-effect nào phụ thuộc vào việc được gọi từ trong `decide_case_approval` (ví dụ transition case trước đó). Đọc lại `decide_case_approval` cho thấy nó tự transition `APPROVED → EXECUTING` trước khi gọi `run_delivery` — vậy `process_due_retries` cần tự làm bước transition này (đã phản ánh trong code trên: `transition(case, "EXECUTING")` trước khi gọi).

**Wiring vào worker (`backend/app/worker.py`):**

```python
async def _ci_scheduler_tick(ctx: dict) -> None:
    from app.core.scheduling.job_keys import JobKey
    from app.core.scheduling.tick import run_leased_tick
    from app.customer_intelligence.scheduler import run_due_schedules

    async with SessionLocal() as db:
        await run_leased_tick(
            db, job_key=JobKey.CI_SCHEDULER_TICK, interval_seconds=300, lease_seconds=240,
            worker_id=_worker_identity(), run=lambda: run_due_schedules(db),
        )

async def _ci_retry_due_cases_tick(ctx: dict) -> None:
    from app.core.scheduling.job_keys import JobKey
    from app.core.scheduling.tick import run_leased_tick
    from app.customer_intelligence.scheduler import process_due_retries

    async with SessionLocal() as db:
        await run_leased_tick(
            db, job_key=JobKey.CI_RETRY_DUE_CASES, interval_seconds=60, lease_seconds=50,
            worker_id=_worker_identity(), run=lambda: process_due_retries(db),
        )
```

**`worker_id` — kết quả tra cứu:** ARQ context (`ctx`) không có field `worker_id` sẵn theo tài liệu chính thức — `ctx` chứa `job_id`, `job_try`, `enqueue_time`, `score`, `redis`, `job_ctx_var`, nhưng không có định danh worker process cố định. Dùng giải pháp thay thế: sinh `worker_id` ổn định một lần lúc `_startup(ctx)` bằng `f"{socket.gethostname()}-{os.getpid()}"`, lưu vào biến module-level, đọc lại trong mỗi tick:

```python
import os, socket
_worker_id: str | None = None

async def _startup(ctx: dict) -> None:
    global _worker_id
    _worker_id = f"{socket.gethostname()}-{os.getpid()}"
    ...

def _worker_identity() -> str:
    return _worker_id or "unknown"
```

Xóa `_scheduler_tick_lock = asyncio.Lock()` khỏi `scheduler.py` — đã được thay thế hoàn toàn bởi lease DB.

**Đăng ký cron mới trong `WorkerSettings.cron_jobs`:**

```python
cron_jobs = [
    cron(_auto_rollback_sweep, minute=set(range(0, 60, 5))),
    cron(_fail_orphaned_chat_runs, minute=set(range(0, 60, 2)), run_at_startup=False),
    cron(_ci_scheduler_tick, minute=set(range(0, 60, 5)), run_at_startup=False),
    cron(_ci_retry_due_cases_tick, minute=set(range(0, 60, 1)), run_at_startup=False),
]
```

**Test:** `backend/tests/test_ci_retry_scheduler.py`:
- case `RETRYING` chưa có report, `next_retry_at` quá khứ → gọi lại research thành công → chuyển `REPORT_READY`.
- case `RETRYING` đã có report (delivery lỗi trước đó), approval `approved` tồn tại → gọi lại delivery thành công → chuyển `COMPLETED`.
- case vượt `MAX_RETRY_COUNT` → `DEAD_LETTER`, không gọi lại provider.
- case `next_retry_at` tương lai → không bị xử lý trong tick này.

### Bước 6 — Endpoint manual retry

**File thay đổi:**
- `backend/app/services/customer_intelligence_service.py` — thêm `retry_case()`:

```python
async def retry_case(self, *, org_id: str, case_id: str, actor_user_id: str) -> ResearchCase:
    from app.repositories.customer_intelligence import ResearchCaseRepository
    case_repo = ResearchCaseRepository(self.db)
    case = await case_repo.get(org_id, case_id)
    if case is None:
        raise ValueError("case not found")
    if case.status not in {"RETRYING", "DEAD_LETTER"}:
        raise ValueError(f"case cannot be retried from status={case.status}")
    previous_status = case.status
    if case.status == "DEAD_LETTER":
        # DEAD_LETTER không có transition hợp lệ sẵn trong CASE_TRANSITIONS ->
        # cần thêm "DEAD_LETTER": {"RETRYING"} vào CASE_TRANSITIONS (bước 4).
        await case_repo.transition(case, "RETRYING")
    updated = await case_repo.schedule_retry(case, next_retry_at=utc_now(), triggered_by=actor_user_id)
    await log_action(
        self.db, org_id=org_id, actor_user_id=actor_user_id, action="ci.case.retry_triggered",
        resource_type="ci_case", resource_id=case_id,
        metadata={"trigger": "manual", "previous_status": previous_status, "retry_count": updated.retry_count},
    )
    return updated
```

**Xác nhận bổ sung transition:** `DEAD_LETTER → RETRYING` cần được thêm vào `CASE_TRANSITIONS` (hiện `DEAD_LETTER` không có key, nghĩa là không transition nào hợp lệ từ đó) — đúng ý định "manual retry có thể hồi sinh case đã dead-letter".

- `backend/app/api/v1/routes/customer_intelligence.py` — route mới:

```python
@router.post(
    "/cases/{case_id}/retry",
    response_model=CaseSummary,
    dependencies=[Depends(require_permission("ci:manage"))],
)
async def retry_case(
    case_id: str,
    org_id: str = Depends(get_current_org_id),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _guard_enabled()
    try:
        case = await CustomerIntelligenceService(db).retry_case(
            org_id=org_id, case_id=case_id, actor_user_id=current_user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return CaseSummary(
        id=case.id, email_id=case.email_id, company_name=case.company_name,
        company_domain=case.company_domain, status=case.status, confidence=case.confidence,
        trigger=case.trigger, created_at=case.created_at, finished_at=case.finished_at,
    )
```

**Test:** `backend/tests/test_ci_case_retry_api.py`:
- retry case `RETRYING` → 200, `retry_count` không đổi (giữ nguyên, không reset), audit log có `trigger=manual`, `actor`.
- retry case `DEAD_LETTER` → 200, case chuyển `RETRYING`.
- retry case `COMPLETED`/`RESEARCHING` → 400.
- retry case không tồn tại → 404 (cần map `ValueError("case not found")` sang 404 riêng, không phải 400 — sửa route để phân biệt 2 loại lỗi).

### Bước 7 — Docker Compose + metrics

**File thay đổi:**
- `docker-compose.yml`, service `worker`:

```yaml
worker:
  restart: unless-stopped
  healthcheck:
    test: ["CMD", "arq", "app.worker.WorkerSettings", "--check"]
    interval: 30s
    timeout: 10s
    retries: 3
    start_period: 20s
```

- `backend/app/core/observability/metrics.py` — thêm 3 metric (bỏ `job_schedule_missed_total` khỏi đợt 1 theo quyết định ở mục 1):

```python
job_schedule_tick_total = Counter(
    "job_schedule_tick_total", "Scheduled job ticks by job_key and result",
    ["job_key", "result"],  # claimed_succeeded | claimed_failed | skipped_lease_held
)
ci_case_retry_total = Counter(
    "ci_case_retry_total", "Customer-intelligence case retries by trigger and outcome",
    ["trigger", "outcome"],  # trigger: auto|manual — outcome: retried|dead_lettered
)
ci_dead_letter_gauge = Gauge("ci_dead_letter_cases", "Current count of cases in DEAD_LETTER status")
```

Wire `job_schedule_tick_total` vào `run_leased_tick` (3 nhánh: `skipped_lease_held` khi `execution is None`, `claimed_succeeded`/`claimed_failed` sau `run()`). Wire `ci_case_retry_total` vào cả `process_due_retries` (trigger=auto) và `retry_case` service method (trigger=manual — chỉ tăng khi thực sự schedule lại, không tăng ở validation error). `ci_dead_letter_gauge` cập nhật bằng một query đơn giản trong `process_due_retries` sau mỗi tick (đếm `COUNT(*) WHERE status='DEAD_LETTER'`) — chấp nhận độ trễ tối đa 1 phút giữa số liệu thật và gauge, đủ cho mục tiêu "biết hệ thống đang ổn hay không".

**Test:** không cần test riêng cho metrics (theo pattern hiện có, `test_scheduler.py` đã có `_counter_value()` helper) — thêm assertion metrics vào test của bước 5/6 thay vì file riêng.

## 3. Danh sách file bị ảnh hưởng (tổng hợp)

**File mới:**
- `backend/app/models/... ` (JobScheduleExecution thêm vào `customer_intelligence.py`, không file riêng)
- `backend/app/repositories/job_schedule.py`
- `backend/app/core/scheduling/__init__.py`
- `backend/app/core/scheduling/job_keys.py`
- `backend/app/core/scheduling/tick.py`
- `backend/app/core/scheduling/backoff.py`
- `backend/alembic/versions/0028_job_scheduling_hardening.py`
- `backend/tests/test_job_schedule_lease.py`
- `backend/tests/test_backoff.py`
- `backend/tests/test_ci_research_retry.py`
- `backend/tests/test_ci_retry_scheduler.py`
- `backend/tests/test_ci_case_retry_api.py`

**File sửa:**
- `backend/app/models/customer_intelligence.py`
- `backend/app/models/__init__.py`
- `backend/app/repositories/customer_intelligence.py` (`CASE_TRANSITIONS`, `ResearchCaseRepository`)
- `backend/app/customer_intelligence/scheduler.py` (`process_due_retries`, xóa `_scheduler_tick_lock`)
- `backend/app/services/customer_intelligence_service.py` (`research_case`, `retry_case`)
- `backend/app/api/v1/routes/customer_intelligence.py` (route retry)
- `backend/app/worker.py` (`_ci_scheduler_tick`, `_ci_retry_due_cases_tick`, `_startup`, `WorkerSettings.cron_jobs`)
- `backend/app/core/observability/metrics.py`
- `docker-compose.yml`

## 4. Rủi ro còn lại cần xác nhận trong lúc code (không block bắt đầu)

1. **Nhánh delivery-retry trong `process_due_retries`** (bước 5) — cần đọc lại `decide_case_approval`/`run_delivery` một lần nữa ngay trước khi viết, xác nhận hướng (b) (query `ApprovalRequest` approved gần nhất, gọi `run_delivery` trực tiếp) không bỏ sót side-effect nào (đặc biệt: `ci_approval_age_seconds` metric hiện chỉ được observe trong `decide_case_approval`, không có trong `run_delivery` — retry qua đường (b) sẽ không tự động có metric này, cần quyết định có cần thêm hay bỏ qua ở đợt 1).
2. **`CASE_TRANSITIONS` cần thêm 2 transition mới:** `RESEARCHING → DEAD_LETTER` và `DEAD_LETTER → RETRYING`. Cần rà lại toàn bộ nơi dùng `CASE_TRANSITIONS` để chắc chắn không có test hiện tại assert transition bị cấm (ví dụ test kỳ vọng `DEAD_LETTER` là trạng thái cuối).
3. **404 vs 400 trong route retry** — route hiện tại của CI dùng pattern khác nhau giữa các endpoint (một số 404 cho "not found", 400 cho business rule) — cần giữ nhất quán khi thêm route mới.

## 5. Tiêu chí hoàn thành

Giữ nguyên theo spec mục 14, bổ sung:

- Case bị lỗi giữa research (giả lập bằng cách mock provider raise exception) tự động chuyển `RETRYING` rồi được `ci_retry_due_cases_tick` nhặt lại và hoàn thành, có bằng chứng test.
- `alembic upgrade head` + `alembic downgrade -1` + `alembic upgrade head` chạy sạch.
- `pytest -q` toàn bộ `backend/tests/test_customer_intelligence*.py`, `test_scheduler.py`, `test_schedule_api.py`, `test_delivery.py` vẫn xanh (không phá test hiện có).
- `python -m ruff check app tests` xanh.
