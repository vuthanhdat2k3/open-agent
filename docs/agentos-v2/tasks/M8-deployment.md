# M8 — Deployment & Scale readiness

## Branch
`agentos-v2/m8-deployment` từ `main` (sau khi M6 và M7 đã merge).

## Scope
**Trong phạm vi**: root `docker-compose.yml` hoàn chỉnh (mọi service của
toàn bộ hệ thống), chuyển DB default sang Postgres, `/readyz`, `.env.example`
gốc, mở rộng CI build image + validate compose, cập nhật README/ARCHITECTURE
gốc trỏ sang `docs/agentos-v2/`.
**Ngoài phạm vi**: Kubernetes/Helm — cố tình không làm theo quyết định đã
chốt ("Docker Compose, 1 host").

## Depends on
M6 (cần `worker`/Redis đã có code), M7 (cần observability app code đã có để
wiring container quan sát).

## Files to add
- `docker-compose.yml` (root — **hiện chưa tồn tại ở root**, chỉ có trong
  `rag-service/` và `mcp-drive-server/`)
- `docker-compose.observability.yml` (hoặc dùng `profiles:` trong file chính
  — chọn 1 cách, khuyến nghị `profiles:` để chỉ cần 1 file)
- `backend/Dockerfile`
- `frontend/Dockerfile`
- `.env.example` (root, gộp mọi biến — khác với `backend/.env.example` hiện
  có, file root này dùng cho `docker compose --env-file`)
- `backend/app/api/v1/routes/health.py` (nếu `/healthz` ở M0 để tạm trong
  `main.py`, tách ra đây kèm `/readyz`)

## Files to modify
- `backend/app/config.py` — đổi `db_url` default sang
  `postgresql+asyncpg://openagent:openagent@postgres:5432/openagent` khi chạy
  trong compose (giữ SQLite làm fallback nếu không set `OPENAGENT_DB_URL`,
  tài liệu rõ trong README: SQLite chỉ cho "chạy nhanh không cần Docker").
- `backend/app/main.py` — thêm `GET /readyz`: kiểm `await db.execute(text("SELECT 1"))`
  + `await redis.ping()` (nếu `workflow_execution_mode=queued` hoặc luôn kiểm
  nếu Redis được cấu hình), trả 503 nếu bất kỳ dependency nào fail.
- `.github/workflows/ci.yml` — thêm job `build-images` (build
  `backend/Dockerfile`, `frontend/Dockerfile`, không push), thêm bước
  `docker compose config` để validate compose file syntax + biến env cần
  thiết đều có mặt trong `.env.example`.
- Root `README.md`, `docs/ARCHITECTURE.md` — thêm banner đầu file: "Tài liệu
  này mô tả kiến trúc v1 (single-user). Xem `docs/agentos-v2/ARCHITECTURE.md`
  cho kiến trúc hiện hành (multi-user AgentOS)." + cập nhật Quick Start trỏ
  sang `docker compose up`.

## Step-by-step
1. Viết `backend/Dockerfile` (multi-stage: builder cài deps, runtime image
   nhẹ `python:3.11-slim`, chạy `alembic upgrade head && uvicorn ...` qua
   entrypoint script) và `frontend/Dockerfile` (multi-stage Next.js build +
   `next start`).
2. Viết `docker-compose.yml` với service tối thiểu trước
   (`postgres, redis, api, worker, frontend`), chạy thử `docker compose up`
   local, xác nhận `api` connect Postgres/Redis đúng, `worker` nhận job.
3. Thêm `qdrant, rag-service` (map theo `rag-service/docker-compose.yml` đã
   có sẵn, port không đụng nhau — rà lại port đã dùng: rag-service REST 8100,
   MCP-SSE 8101).
4. Thêm `mcp-drive-server` dưới `profiles: [optional]` (không phải service
   bắt buộc, vì cần OAuth setup thủ công).
5. Thêm profile `observability` (`otel-collector, prometheus, grafana, loki,
   promtail`) — copy cấu hình cơ bản, point `otel-collector` xuất metric ra
   Prometheus, log ra Loki qua Promtail đọc Docker log driver.
6. Thêm `/readyz`, test bằng cách tắt Postgres container → assert `/readyz`
   trả 503, bật lại → 200.
7. Cập nhật CI: build image (không push), `docker compose config` validate.
8. Cập nhật README/ARCHITECTURE gốc.

## Suggested commit breakdown
1. `feat(agentos-m8): backend + frontend production dockerfiles`
2. `feat(agentos-m8): root docker-compose.yml (postgres, redis, api, worker, frontend)`
3. `feat(agentos-m8): wire qdrant + rag-service into compose`
4. `feat(agentos-m8): optional mcp-drive-server profile in compose`
5. `feat(agentos-m8): observability profile (otel-collector, prometheus, grafana, loki)`
6. `feat(agentos-m8): /readyz endpoint checking db + redis connectivity`
7. `ci(agentos-m8): build docker images + validate compose config in CI`
8. `docs(agentos-m8): point README/ARCHITECTURE to agentos-v2 as current architecture`

## Tests to write
- `test_readyz.py`: mock DB session raise exception → `/readyz` trả 503;
  DB+Redis OK → 200.
- Không cần unit test cho Dockerfile/compose — xác minh bằng chạy tay + ghi
  lại kết quả trong PR description (mục "Manual verification" — xem PR
  checklist).

## CI additions
```yaml
  build-images:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: docker build -t openagent-api ./backend
      - run: docker build -t openagent-frontend ./frontend
      - run: docker compose config
```
(Không push image trong v1 — chỉ đảm bảo build được + compose file hợp lệ.)

## PR checklist
```
- [ ] docker compose up từ máy sạch dựng được toàn bộ stack cơ bản (postgres/redis/api/worker/frontend)
- [ ] api + worker báo healthy qua compose healthcheck (dùng /healthz, /readyz)
- [ ] qdrant + rag-service chạy đúng trong cùng compose, backend connect MCP tới rag-service thành công
- [ ] Profile observability bật được riêng (--profile observability), không bắt buộc cho dev thường
- [ ] mcp-drive-server là optional profile, không bắt buộc để stack chính chạy được
- [ ] /readyz trả 503 khi Postgres/Redis down, 200 khi khoẻ
- [ ] CI build image + validate compose xanh
- [ ] README/ARCHITECTURE gốc đã trỏ rõ sang docs/agentos-v2 là kiến trúc hiện hành
- [ ] Manual verification note trong PR: đã tự chạy docker compose up và xác nhận (đính kèm log/step đã làm)
```
