# Spec: Hardening scheduler/worker cho production (Hướng A)

> Trạng thái: chờ review  
> Phạm vi: đợt 1 — wire `_ci_scheduler_tick` vào lease chung; đợt 2 (backlog) — wire các cron job còn lại  
> Không thuộc phạm vi: Temporal, tách scheduler thành service riêng, UI operations

## 1. Bối cảnh và mục tiêu

Hệ thống hiện chạy ARQ worker với cron jobs (`_auto_rollback_sweep`, `_fail_orphaned_chat_runs`, `_ci_scheduler_tick`) nhưng:

- không có lease cấp tick → nếu scale worker lên nhiều replica, hai worker có thể cùng chạy một tick;
- `CiSchedule`/`ResearchCase` retry chưa có backoff, dead-letter thao tác được, hay phân biệt auto retry vs manual retry;
- worker container chưa có healthcheck/restart policy rõ ràng;
- thiếu metrics tối thiểu để biết hệ thống đang ổn hay không.

Mục tiêu: đạt "không mất job khi worker crash" và "biết chính xác job đang ở đâu" ở quy mô vài chục tổ chức, vài trăm email/ngày, vận hành bởi 1 người — không thêm hạ tầng mới (Redis/PostgreSQL hiện có là đủ).

Quyết định đã chốt (từ brainstorming trước):

1. Bảng lease generic, không gắn cứng CI — đợt 1 chỉ wire CI, đợt 2 (backlog) wire job còn lại.
2. Hai lớp riêng biệt: lease cấp tick (`JobScheduleExecution`) và retry cấp case (`ResearchCase.retry_count`/`next_retry_at`) — không gộp, không tạo bảng `ci_dead_letters` riêng.
3. API-only cho manual retry, không UI. Phải ghi nhận ai/khi trigger retry thủ công.
4. Additive migration, review schema trước khi viết Alembic.

## 2. Schema

### 2.1. Bảng mới: `job_schedule_executions`

```python
class JobScheduleExecution(Base):
    __tablename__ = "job_schedule_executions"
    __table_args__ = (
        UniqueConstraint("job_key", "scheduled_for", name="uq_job_schedule_key_time"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    job_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    scheduled_for: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    lease_owner: Mapped[str] = mapped_column(String(64), nullable=False)
    lease_expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="running", nullable=False, index=True)
    attempt: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    result_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
```

Không có FK tới `organizations` vì job có thể chạy toàn hệ thống (không thuộc một org).

`job_key` là string tự do (không enum DB). Ở tầng application, định nghĩa constant để tránh lỗi chính tả khi wire job mới:

```python
# app/core/scheduling/job_keys.py
class JobKey:
    CI_SCHEDULER_TICK = "ci_scheduler_tick"
    AUTO_ROLLBACK_SWEEP = "auto_rollback_sweep"       # đợt 2, chưa wire
    FAIL_ORPHANED_CHAT_RUNS = "fail_orphaned_chat_runs"  # đợt 2, chưa wire
```

`status` values: `running | succeeded | failed`.

### 2.2. Cột mới trên `ci_cases` (bảng đang có dữ liệu — additive only)

```python
retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False, server_default="0")
next_retry_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
last_retry_triggered_by: Mapped[str | None] = mapped_column(
    String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
)
```

`server_default="0"` cho `retry_count` để `ALTER TABLE ... ADD COLUMN` không cần backfill và không lock bảng lâu trên Postgres hiện đại. Hai cột còn lại nullable, không default cần backfill.

Ý nghĩa `last_retry_triggered_by`:
- `None` → lần retry gần nhất là tự động (scheduler/worker).
- `user_id` → người dùng tự bấm retry qua API.

### 2.3. Cleanup `job_schedule_executions` (backlog, không làm ngay)

Ghi chú backlog: cleanup dựa trên `finished_at`, retention khác nhau theo status — `succeeded` giữ 14 ngày, `failed` giữ 90 ngày (lịch sử lỗi hữu ích hơn khi điều tra pattern).

## 3. Repository layer

### 3.1. `JobScheduleExecutionRepository`

Không kế thừa `BaseRepository` thông thường vì `BaseRepository.get/list/create` giả định luôn có `org_id` filter — bảng này không có `org_id`. Viết repository riêng:

```python
class JobScheduleExecutionRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def try_claim(
        self, *, job_key: str, scheduled_for: datetime, lease_owner: str, lease_seconds: int
    ) -> JobScheduleExecution | None:
        """Atomic claim qua SAVEPOINT + unique constraint.

        Trả về record nếu claim thành công (mình là worker được chạy tick
        này). Trả về None nếu IntegrityError (worker khác đã claim) — không
        raise, để caller return sớm mà không cần try/except ở nơi gọi.
        """
        lease_expires_at = utc_now() + timedelta(seconds=lease_seconds)
        execution = JobScheduleExecution(
            job_key=job_key,
            scheduled_for=scheduled_for,
            lease_owner=lease_owner,
            lease_expires_at=lease_expires_at,
            status="running",
        )
        try:
            async with self.db.begin_nested():  # SAVEPOINT — không phá transaction ngoài
                self.db.add(execution)
                await self.db.flush()
        except IntegrityError:
            return None
        await self.db.commit()
        return execution

    async def mark_succeeded(self, execution: JobScheduleExecution, *, result_summary: dict) -> None: ...
    async def mark_failed(self, execution: JobScheduleExecution, *, error: str) -> None: ...
```

**Quyết định đã chốt:** dùng `db.begin_nested()` (SAVEPOINT) + try/except `IntegrityError`, không dùng `INSERT ... ON CONFLICT DO NOTHING`. Lý do: `ON CONFLICT` đòi hỏi constructor dialect-specific (`sqlalchemy.dialects.postgresql.insert()` vs `sqlalchemy.dialects.sqlite.insert()`) — nghĩa là `try_claim` phải rẽ nhánh theo dialect, tạo rủi ro lệch hành vi giữa test (SQLite) và production (Postgres). SAVEPOINT hoạt động giống nhau trên cả hai dialect qua SQLAlchemy generic API, và tự nhiên giải quyết lo ngại "rollback side effect giữa transaction đang mở": SAVEPOINT chỉ rollback phần insert thất bại, không ảnh hưởng session cha.

### 3.2. Thay đổi `ResearchCaseRepository`

Thêm method:

```python
async def schedule_retry(
    self, case: ResearchCase, *, next_retry_at: datetime, triggered_by: str | None
) -> ResearchCase:
    """Chuyển case sang RETRYING, tăng retry_count, set next_retry_at và
    last_retry_triggered_by. triggered_by=None nghĩa là tự động."""

async def list_due_for_retry(self, now: datetime, *, limit: int = 50) -> list[ResearchCase]:
    """Case ở RETRYING với next_retry_at <= now."""
```

Không đổi `CASE_TRANSITIONS` hiện có — `RETRYING` đã hợp lệ transition tới `RESEARCHING/EXECUTING/DEAD_LETTER`.

## 4. Backoff policy

```python
# app/core/scheduling/backoff.py
def compute_backoff_seconds(retry_count: int, *, base: int = 60, cap: int = 3600) -> float:
    """Exponential backoff + full jitter: random(0, min(cap, base * 2^retry_count))."""

MAX_RETRY_COUNT = 5  # vượt quá → chuyển DEAD_LETTER, không tiếp tục retry
```

Áp dụng full jitter (không phải equal jitter) để tránh nhiều case cùng retry_count đồng loạt retry cùng lúc — đúng khuyến nghị AWS Architecture Blog cho exponential backoff.

Lỗi tạm thời (network, timeout, provider 5xx) → `RETRYING`. Lỗi auth/validation (invalid recipient, missing credentials) → không retry, giữ nguyên trạng thái lỗi hiện có (không đổi hành vi hiện tại của `delivery.py`/`workflow.py` ngoài phạm vi retry).

## 5. Wiring vào `_ci_scheduler_tick` (đợt 1)

Thay đổi trong `app/worker.py`:

```python
async def _ci_scheduler_tick(ctx: dict) -> None:
    from app.core.scheduling.job_keys import JobKey
    from app.core.scheduling.tick import run_leased_tick
    from app.customer_intelligence.scheduler import run_due_schedules

    async with SessionLocal() as db:
        await run_leased_tick(
            db,
            job_key=JobKey.CI_SCHEDULER_TICK,
            interval_seconds=300,  # khớp cron minute=set(range(0,60,5))
            lease_seconds=240,     # < interval để tick sau không bị block nếu lease cũ hết hạn muộn
            worker_id=ctx.get("worker_id", "unknown"),
            run=lambda: run_due_schedules(db),
        )
```

`run_leased_tick` là helper generic (đúng tinh thần hạ tầng dùng chung):

```python
# app/core/scheduling/tick.py
async def run_leased_tick(
    db: AsyncSession,
    *,
    job_key: str,
    interval_seconds: int,
    lease_seconds: int,
    worker_id: str,
    run: Callable[[], Awaitable[dict]],
) -> None:
    """Làm tròn now() về interval_seconds gần nhất → scheduled_for.
    Claim qua JobScheduleExecutionRepository.try_claim.
    Nếu claim thất bại (None) → log debug và return (worker khác đã chạy).
    Nếu claim thành công → chạy `run()`, mark_succeeded/mark_failed theo kết quả.
    Không raise ra ngoài — lỗi luôn được ghi vào execution record, không crash worker.
    """
```

Việc này thay thế hoàn toàn `_scheduler_tick_lock = asyncio.Lock()` hiện có trong `scheduler.py` (chỉ hoạt động trong 1 process). Cần xóa lock cũ khi migrate, tránh double-locking gây confuse.

### Xử lý `worker_id`

ARQ context (`ctx`) có sẵn thông tin định danh job/worker theo tài liệu ARQ; cần xác nhận field chính xác (`job_id` hay cần tự sinh) khi implement — nếu không có sẵn, sinh `worker_id` ổn định theo hostname + PID lúc `_startup`.

## 6. Manual retry endpoint (API-only)

Thêm route mới trong `customer_intelligence.py`:

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
    """Retry thủ công một case đang RETRYING hoặc DEAD_LETTER.

    Chỉ cho phép retry từ RETRYING/DEAD_LETTER — không cho retry case đang
    RESEARCHING/EXECUTING (đang chạy) hoặc đã COMPLETED/REJECTED (đã kết thúc
    hợp lệ, retry không có nghĩa).
    """
```

Service method `CustomerIntelligenceService.retry_case()`:

- validate case.status in {RETRYING, DEAD_LETTER};
- reset `retry_count` giữ nguyên (không reset về 0 — manual retry vẫn tính vào tổng số lần thử, tránh vòng lặp vô hạn nếu user bấm retry liên tục sau khi đã DEAD_LETTER);
- gọi `schedule_retry(case, next_retry_at=utc_now(), triggered_by=current_user.id)`;
- ghi `log_action(..., action="ci.case.retry_triggered", metadata={"triggered_by": "manual", "actor": current_user.id, "previous_status": ...})` — dùng `log_action` hiện có, `org_id` lấy từ case (luôn có sẵn ở cấp case, không phải vấn đề như lease tick).
- enqueue lại research job (theo cơ chế queue của mục 7).

Response trả về case đã update, để bạn (qua curl/Postman) thấy ngay `status`/`retry_count` mới.

## 7. Retry tự động — job xử lý case RETRYING

Cần một cron job mới (`ci_retry_due_cases`, `job_key = "ci_retry_due_cases"`) chạy song song với `_ci_scheduler_tick`, dùng cùng `run_leased_tick`:

```python
async def _ci_retry_due_cases_tick(ctx: dict) -> None:
    async with SessionLocal() as db:
        await run_leased_tick(
            db,
            job_key=JobKey.CI_RETRY_DUE_CASES,
            interval_seconds=60,
            lease_seconds=50,
            worker_id=...,
            run=lambda: _process_due_retries(db),
        )

async def _process_due_retries(db: AsyncSession) -> dict:
    """list_due_for_retry() → với mỗi case: nếu retry_count > MAX_RETRY_COUNT
    → transition DEAD_LETTER; ngược lại → gọi lại run_research() hoặc
    run_delivery() tùy case đang RETRYING ở bước nào; lỗi lại → schedule_retry
    với backoff tăng dần."""
```

**Điểm cần xác nhận khi implement:** `ResearchCase.status = RETRYING` hiện dùng chung cho cả lỗi ở bước research (`workflow.py`) và lỗi ở bước delivery (`delivery.py`) — theo `CASE_TRANSITIONS`, `RETRYING → {RESEARCHING, EXECUTING, DEAD_LETTER}`. Cần thêm cách phân biệt "case này retry nên gọi lại research hay lại gọi delivery" — đề xuất dùng cột có sẵn: nếu `case.workflow_run_id` đã set và có `BriefingReport` → retry nghĩa là gọi lại delivery (`run_delivery` qua approval đã approved); nếu chưa có report → gọi lại `run_research`. Cần review code `workflow.py`/`delivery.py` kỹ hơn ở bước viết plan để xác nhận đúng transition trước khi code — ghi vào plan như một open question, không tự quyết định ngay trong spec này.

## 8. Docker Compose healthcheck/restart

Thay đổi trong `docker-compose.yml`, service `worker`:

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

**Đã xác nhận:** ARQ hỗ trợ `--check` — nó connect Redis và kiểm tra sentinel key (`health_check_key`), trả về exit code 0/1 đúng hành vi healthcheck cần. Dùng thẳng như trên, không cần script thay thế.

Lưu ý đã biết (ARQ issue #291): health-check key có thể bị xóa khi worker shutdown, gây healthcheck fail giả trong lúc restart. Không ảnh hưởng đáng kể ở quy mô hiện tại (1 worker container trên Docker Compose, không phải multi-replica K8s) — chấp nhận rủi ro này, không cần workaround.

`api` service đã có `restart: unless-stopped` theo compose hiện tại — cần đối chiếu để đồng bộ policy.

## 9. Metrics tối thiểu

Thêm vào `app/core/observability/metrics.py`, cùng khu vực `Customer Intelligence (M6)` đã có:

```python
job_schedule_tick_total = Counter(
    "job_schedule_tick_total",
    "Scheduled job ticks by job_key and result",
    ["job_key", "result"],  # result: claimed_succeeded | claimed_failed | skipped_lease_held
)
job_schedule_missed_total = Counter(
    "job_schedule_missed_total",
    "Ticks where scheduled_for passed without any successful claim before the next tick",
    ["job_key"],
)
ci_case_retry_total = Counter(
    "ci_case_retry_total",
    "Customer-intelligence case retries by trigger and outcome",
    ["trigger", "outcome"],  # trigger: auto|manual — outcome: retried|dead_lettered
)
ci_dead_letter_gauge = Gauge(
    "ci_dead_letter_cases",
    "Current count of cases in DEAD_LETTER status",
)
```

Giữ đúng convention label bounded đã ghi trong comment hiện có (không đưa `org_id`/`case_id` vào label).

`job_schedule_missed_total` cần logic riêng: so sánh `scheduled_for` mong đợi (theo `interval_seconds`) với execution record thực tế có `status=succeeded` — nếu thiếu, tăng counter ở tick kế tiếp. Đây là phần phức tạp nhất trong việc đo missed run; cần thiết kế chi tiết hơn ở bước plan/code, spec này chỉ định nghĩa mục tiêu đo, chưa chốt thuật toán.

## 10. Migration file

`backend/alembic/versions/0028_job_scheduling_hardening.py`, `down_revision = "0027_approval_owning_task"` (cần xác nhận đúng revision id của `0027` khi mở file, chưa đọc nội dung file này trong phiên brainstorming — sẽ đọc trước khi viết migration thật).

Nội dung migration (additive only, không backfill phức tạp):

1. `create_table("job_schedule_executions", ...)` + unique constraint + 2 index (`job_key`, `status`).
2. `add_column("ci_cases", "retry_count", ..., server_default="0")`.
3. `add_column("ci_cases", "next_retry_at", ...)`.
4. `add_column("ci_cases", "last_retry_triggered_by", ..., ForeignKey users.id ondelete SET NULL)`.

`downgrade()` đối xứng: drop 3 cột trên `ci_cases`, drop 2 index + bảng `job_schedule_executions`.

## 11. Test plan

- `test_job_schedule_lease.py`:
  - hai lời gọi `try_claim` cùng `job_key`+`scheduled_for` → chỉ một thành công.
  - `try_claim` với `scheduled_for` khác nhau (tick khác) → cả hai thành công.
  - `mark_succeeded`/`mark_failed` cập nhật đúng `status`/`finished_at`.
- `test_ci_retry.py`:
  - case `RETRYING` với `next_retry_at` quá khứ → `list_due_for_retry` trả về.
  - case `RETRYING` với `next_retry_at` tương lai → không trả về.
  - vượt `MAX_RETRY_COUNT` → chuyển `DEAD_LETTER`, không tiếp tục retry.
  - manual retry qua API → `last_retry_triggered_by` = user id, audit log có action `ci.case.retry_triggered`.
  - auto retry → `last_retry_triggered_by` = None.
  - retry case không ở `RETRYING`/`DEAD_LETTER` → API trả 400.
- `test_worker_leased_tick.py` (nếu tách `run_leased_tick` là unit test được): giả lập lease đã tồn tại và chưa hết hạn → tick thứ hai bị skip; lease hết hạn → tick mới được claim lại (crash recovery).

Toàn bộ test dùng SQLite in-memory theo pattern hiện có trong `test_scheduler.py`, không cần Postgres riêng. Vì `try_claim` dùng `db.begin_nested()` + `IntegrityError` (generic SQLAlchemy API, không phải dialect-specific `ON CONFLICT`), hành vi giữa SQLite (test) và Postgres (production) đã được xác nhận nhất quán — không còn là rủi ro kỹ thuật mở của spec này.

## 12. Rủi ro và open questions

Đã chốt trong review:

- **Atomic claim (dialect SQLite vs Postgres):** dùng `db.begin_nested()` (SAVEPOINT) + try/except `IntegrityError`, không dùng `ON CONFLICT DO NOTHING`. Chi tiết ở mục 3.1.
- **ARQ health-check flag `--check`:** xác nhận hỗ trợ, dùng thẳng như mục 8. Rủi ro nhỏ đã biết (issue #291, health-check-key bị xóa lúc shutdown) chấp nhận được ở quy mô 1 worker container.

Còn để mở, chuyển sang bước viết plan chi tiết (cần đọc code thật, không suy luận từ spec):

1. **Case RETRYING ở bước research vs delivery** — cần đọc kỹ `workflow.py`/`delivery.py` transition thực tế trước khi quyết định cách `_process_due_retries` biết phải gọi lại hàm nào. Đoán sai ở đây có thể khiến retry một case đã có report bằng cách chạy lại research, gây tốn công hoặc tạo report trùng — cần context code thật, không suy luận.
2. **`ctx["worker_id"]` có thật sự tồn tại trong ARQ context không** — cần kiểm tra tài liệu/behaviour thực tế của phiên bản ARQ đang dùng.
3. **`job_schedule_missed_total` thuật toán đo missed run** — chưa chốt, cần thiết kế riêng hoặc tạm bỏ ở đợt 1 nếu quá phức tạp so với lợi ích (có thể để đợt 2).

## 13. Ngoài phạm vi đợt 1 (backlog, không làm trong lần triển khai này)

- Wire `_auto_rollback_sweep`, `_fail_orphaned_chat_runs` vào `run_leased_tick` (đợt 2).
- Cleanup job cho `job_schedule_executions` theo retention 14/90 ngày.
- UI operations cho retry/dead-letter (chỉ API ở đợt 1).
- Reconciliation tự động khi provider đã gửi nhưng DB chưa cập nhật (đã có ghi chú trong `delivery.py` hiện tại, không mở rộng ở spec này).

## 14. Tiêu chí hoàn thành (đợt 1)

- Hai worker container cùng chạy `_ci_scheduler_tick` tại một thời điểm → chỉ một xử lý, có bằng chứng test.
- Case lỗi tạm thời tự động retry với backoff, tối đa `MAX_RETRY_COUNT` lần rồi vào `DEAD_LETTER`.
- Gọi `POST /cases/{id}/retry` thành công, response và audit log phân biệt rõ manual vs auto.
- `pytest -q` xanh cho toàn bộ test mới, không phá vỡ test CI hiện có (`test_scheduler.py`, `test_schedule_api.py`, `test_delivery.py`, `test_customer_intelligence_core.py`).
- Alembic `upgrade`/`downgrade` chạy sạch trên SQLite test DB và không phá schema hiện có.
