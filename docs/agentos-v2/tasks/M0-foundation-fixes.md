# M0 — Sửa lỗi nền tảng + CI tối thiểu

## Branch
`agentos-v2/m0-foundation-fixes` từ `main`.

## Scope
**Trong phạm vi**: fix bug async/sync đã xác nhận bằng test thật, dọn config
chết, dựng CI backend+frontend, thêm healthcheck endpoint.
**Ngoài phạm vi**: không đụng vào auth/RBAC/guardrail (các milestone sau) —
đây thuần là dọn nợ kỹ thuật + an toàn lưới (CI) trước khi thêm bất cứ gì mới.

## Depends on
Không phụ thuộc gì — làm đầu tiên, độc lập hoàn toàn với các milestone khác.

## Files to modify
- `backend/app/core/tools/builtins.py` — dòng 26, đổi `def _read_attachment`
  → `async def _read_attachment`.
- `backend/app/core/tools/filesystem.py` — dòng 26, 44, 76: đổi `def
  _write_file/_list_dir/_search_files` → `async def`.
- `backend/tests/test_tools.py` — sửa `test_save_and_call_memory`: gọi
  `save_memory`/`call_memory` bằng schema hiện tại
  (`memory_type`, `attribute`, `value`) thay vì `key`/`value` cũ; đảm bảo
  `ToolContext` có `agent_id` set khi test (đọc `core/tools/memory.py` và
  `core/memory_schema.py` để lấy đúng tên tham số trước khi sửa).
- `backend/app/config.py` — xoá 3 dòng `loop_warn`, `loop_block`,
  `loop_circuit` (dead config, không ai đọc). Grep lại toàn repo để chắc
  chắn không còn reference nào trước khi xoá.
- `backend/app/main.py` — thêm route `GET /healthz` trả `{"status": "ok"}`,
  không dependency DB/Redis (liveness thuần).

## Files to add
- `.github/workflows/ci.yml`

```yaml
name: CI
on:
  pull_request:
  push:
    branches: [main]
jobs:
  backend:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: backend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install -e ".[dev]"
      - run: ruff check .
      - run: pytest -q
  frontend:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: frontend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: "20" }
      - run: npm ci
      - run: npm run lint
      - run: npx tsc --noEmit
      - run: npm run build
```

(Điều chỉnh tên script `lint`/`build` theo đúng `frontend/package.json` nếu
khác — kiểm tra trước khi copy nguyên văn.)

## Step-by-step
1. Grep toàn repo `loop_warn|loop_block|loop_circuit` để xác nhận dead code
   trước khi xoá (nếu có reference nào lọt, xử lý reference đó trước).
2. Sửa 4 hàm sync → async (builtins.py, filesystem.py).
3. Chạy `pytest backend/tests/test_tools.py -q` — xác nhận 2 test await-bug
   trước đó giờ pass.
4. Sửa `test_save_and_call_memory` theo schema mới, chạy lại tới khi cả
   5/5 test pass.
5. Thêm `/healthz`, test thủ công bằng `curl localhost:8000/healthz`.
6. Thêm `.github/workflows/ci.yml`, push branch, mở PR nháp để tự kiểm tra
   CI chạy được (không cần merge ngay).

## Suggested commit breakdown
1. `fix(agentos-m0): make filesystem/attachment tools async to match ToolSpec.run contract`
2. `fix(agentos-m0): update memory tool test to current schema`
3. `chore(agentos-m0): remove dead loop_warn/loop_block/loop_circuit config`
4. `feat(agentos-m0): add /healthz liveness endpoint`
5. `ci(agentos-m0): add backend + frontend CI workflow`

## Tests to write
- Không cần test mới cho fix async (test cũ đã có, chỉ cần pass).
- `backend/tests/test_health.py`: `GET /healthz` trả `200` + body
  `{"status": "ok"}`, không cần DB fixture (test nhanh, không async DB
  session nào được inject).

## CI additions
Đây chính là milestone tạo CI — không có CI nào trước đó để so sánh. Yêu cầu
tối thiểu: cả 2 job (`backend`, `frontend`) phải xanh trên PR của chính
milestone này trước khi merge (self-validating).

## PR checklist
```
- [ ] 4 tool (read_attachment, write_file, list_dir, search_files) đã async, `await spec.run(...)` không còn TypeError
- [ ] pytest backend/tests: 5/5 (hoặc nhiều hơn nếu đã thêm test_health) pass
- [ ] loop_warn/loop_block/loop_circuit đã xoá khỏi config.py, grep xác nhận không còn reference
- [ ] GET /healthz trả 200 không cần DB
- [ ] .github/workflows/ci.yml tồn tại, cả 2 job xanh trên chính PR này
- [ ] Không có thay đổi ngoài phạm vi M0 (không đụng auth/RBAC/guardrail)
```
