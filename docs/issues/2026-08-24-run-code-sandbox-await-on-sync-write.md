# Issue: `run_code` sandbox fails on every invocation — `await` on sync `StreamWriter.write()`

- **Ngày phát hiện:** 2026-08-24
- **Phát hiện qua:** E2E test chat với agent Coder (org DAT) — `run_code` fail 5/5 lần
- **Mức độ:** Critical — toàn bộ capability chạy code của các agent (Coder…) bị tê liệt
- **Trạng thái:** Open (chưa fix)

## Triệu chứng

Mọi lời gọi tool `run_code` trả về ngay lập tức:

```
error executing sandbox: object NoneType can't be used in 'await' expression
```

Agent rơi vào vòng lặp retry (quan sát thực tế: 5 lần fail liên tiếp trong 1m02s,
7 tool calls) rồi buộc phải tính toán thủ công thay vì chạy code.

## Root cause

File `backend/app/core/tools/sandbox.py`, hàm `_run_code()` (line ~341):

```python
if proc.stdin:
    await proc.stdin.write(archive)   # ← BUG
    await proc.stdin.drain()
    proc.stdin.close()
```

`proc.stdin` là `asyncio.StreamWriter`. Phương thức `write()` là **sync và trả về
`None`** → `await None` → `TypeError: object NoneType can't be used in 'await' expression`,
rơi vào catch-all ở cuối hàm (`error executing sandbox: {e}`) và fail toàn bộ request.

So sánh cùng file, hàm `stream_sandbox_execution()` (line ~197, dùng bởi route
`/api/sandbox` và workspace run) viết ĐÚNG:

```python
proc.stdin.write(str(code).encode("utf-8"))  # sync, không await
await proc.stdin.drain()                      # drain() mới là coroutine
proc.stdin.close()
```

→ Chỉ `_run_code` bị; đường sandbox API/workspace không ảnh hưởng.

## Cách sửa đề xuất

Bỏ `await` ở line 341:

```python
proc.stdin.write(archive)
await proc.stdin.drain()
proc.stdin.close()
```

## Test cần thêm (regression)

Test hiện có (`backend/tests/test_tools.py::test_run_code_workspace_archive_includes_existing_files`)
không bắt được vì không đi qua đường subprocess thật. Cần một test unit mock
`asyncio.create_subprocess_exec` trả về proc giả với `stdin` là `StreamWriter` stub,
assert `_run_code` hoàn thành không raise TypeError — hoặc tối thiểu assert
không có `await` trên method sync qua code review/CI lint.

## Phạm vi liên quan

- Agent nào có tool `run_code` đều bị (Coder trong org DAT confirmed)
- `run_shell` bị chặn riêng bởi RBAC risk-tier (đúng thiết kế, không phải bug này)
- `write_file` không ảnh hưởng (đã verify hoạt động trong cùng session test)
