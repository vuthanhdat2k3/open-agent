# Frontend URL Conventions

> Quy ước URL cho frontend OpenAgent (Next.js App Router). Áp dụng từ P1
> (chat session URL). Cập nhật: 2026-08-25.

## Nguyên tắc

| Loại state | Nơi sống | Ví dụ |
|---|---|---|
| **Entity identity** (đối tượng đang mở) | **URL** (path segment hoặc searchParam) | session đang chat, agent đang chọn |
| **Filters / view options** | **URL searchParams** | bộ lọc danh sách, tab |
| **Transient** (sống ngắn, không cần share) | Zustand store / React state | activeRunId, typewriter buffer, draft |
| **Cross-cutting context** | Cookie/localStorage | active org, theme |

- URL luôn phản ánh đúng trạng thái: refresh, share link, Back/Forward đều hoạt động.
- `router.replace(..., { scroll: false })` khi đồng bộ — không spam history.
- API vẫn là lớp enforcement cuối: deep-link vào vùng không có quyền → 403.

## Chat (P1 — đã triển khai)

```
/chat?agent={agentId}&session={sessionId}
```

- `agent`: bắt buộc trong URL khi trang ổn định; `session`: có khi đang mở hội thoại.
- **Store → URL**: effect mirror dùng `router.replace` — address bar luôn khớp.
- **URL → store (adoption)**: deep-link `?session=` chỉ được nhận khi session
  tồn tại trong org và thuộc agent đang chọn; dead link → về `/chat?agent=X`.
- Guard `if (urlSession && urlSession !== sessionId) return;` chờ adoption
  settles — bỏ guard này sẽ tạo ping-pong loop giữa 2 effect.
- Store (`useChatStore`) vẫn persist để khôi phục nhanh, nhưng URL là nguồn
  hiển thị; 2 tab khác nhau có thể mở 2 session độc lập.

## Các trang khác (backlog P2)

| Trang | Đề xuất | Ghi chú |
|---|---|---|
| `/evaluations` | `?suite=&run=` | suite/run hiện đang là state |
| `/customer-intelligence` | `?case=` | case detail hiện là state |
| `/debug` | `?session=&run=` | cây debug hiện là state |
| `/workflows` | `?run=` khi xem run detail | run detail hiện là state |
| Org context | giữ cookie/localStorage | context xuyên suốt, không đưa vào từng URL |

## Đã có sẵn (đúng convention)

- `/agents/[id]/a2a` — entity identity ở path segment
- `/approvals?approval_id=` — deep-link approval
- `/chat?agent=` — preselect agent
