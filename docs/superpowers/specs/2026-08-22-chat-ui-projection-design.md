# Chat UI Projection Layer — Design

> 2026-08-22 · Branch `feat/chat-ui-projection` · Backend changes: **none**

## Vấn đề

UI chat hiện tại tích lũy state mệnh lệnh (`meta.tools: any[]`, chuỗi nối tay trong `page.tsx`) khiến:

1. Tool calls hiển thị kém — card call và result tách rời, không match nhau
2. Reasoning chỉ hiện khi bật Debug
3. Stats (tokens/cost/latency/model) chỉ hiện khi có cost metadata
4. Stream text nhảy cục — đã có typewriter nhưng neo vào shape message cũ

Mô hình tham chiếu: DeepSeek Harness — *mọi thứ render được đều derive từ event log qua một reducer thuần* ("model-visible means logged" phiên bản UI).

## Kiến trúc

```
SSE events (token/tool_call/tool_result/...)      Persisted transcript (DB)
        │                                                  │
        ▼                                                  ▼
applyChatEvent(state, ev)   ← CÙNG REDUCER →   messagesFromPersisted(rows)
        └──────────────────┬───────────────────────────────────┘
                           ▼
              ChatMessage[] (typed view nodes)
       UserMessage | AssistantMessage(blocks[]) | Approval | Error
                           ▼
   ChatThread → MessageItem(blocks) → TextBlock | ReasoningRow
                                       ToolCallCard | StatsLine
```

### Module mới

| File | Vai trò |
|---|---|
| `frontend/lib/chat/projection.ts` | Types + `createRunProjection()` + `applyChatEvent()` (pure) + `messagesFromPersisted()` |
| `frontend/lib/chat/projection.test.ts` | Unit tests reducer (vitest) |
| `frontend/components/chat/blocks/text-block.tsx` | Lazy markdown + con trỏ nhấp nháy khi streaming |
| `frontend/components/chat/blocks/reasoning-row.tsx` | Collapsible, luôn hiển thị khi có reasoning (không gate theo debug), shimmer khi đang stream |
| `frontend/components/chat/blocks/tool-call-card.tsx` | Gộp call+result thành MỘT card: status icon, args collapsible, live progress, result section, SVG preview |
| `frontend/components/chat/blocks/stats-line.tsx` | Dòng monospace: ↑in ↓out · Xs · $cost · N tools · model — luôn render sau done |
| `frontend/components/chat/run-timeline-panel.tsx` | Sheet drawer: replay toàn bộ event log của run từ `GET /api/chat/runs/{id}/events?follow=false` |
| `frontend/components/chat/delegation-tree.tsx` | Cây sub-agent từ `GET /api/debug/tasks/{root_run_id}` |

### Block model (assistant message)

```ts
type AssistantBlock =
  | { kind: "reasoning"; id; content; streaming }
  | { kind: "tool_call"; id; callIndex; name; argsText; result?; progress?;
      status: "running" | "done" | "error" }
  | { kind: "text"; id; content; streaming }
  | { kind: "stats"; id; tokensIn?; tokensOut?; costUsd?; latencyMs?; model?; toolCount? }
```

Blocks giữ **thứ tự arrival thật** của events: reasoning → token(text) → tool_call → token(text tiếp)… Token append vào text block cuối nếu block cuối là text, ngược lại tạo text block mới. `tool_result` match với `tool_call` đang mở cùng `callIndex`.

### Tính chất bất biến phải giữ

1. **Live ≡ Replay**: cùng chuỗi events qua reducer sinh cùng state — id block sinh deterministic (counter, không dùng Date.now trong reducer).
2. **Backend 0 thay đổi**: mọi endpoint đã tồn tại (`follow=false` snapshot, `/debug/tasks/{root_run_id}`).
3. **Recovery effects của page.tsx giữ nguyên hành vi**: reload-recovery, terminal sync race, approval resume — chỉ đổi nguồn dữ liệu sang projection.

### Smooth streaming (reveal buffer)

Reducer lưu **full content** ngay khi nhận. Reveal buffer (RAF, ~3 chars/frame — giữ nguyên cơ chế đã tune của page cũ) nằm giữa store và DOM, áp cho block `status=streaming`; block done → hiện full tức thì. Replay path: blocks đến sẵn complete → không qua buffer → render instant.

### Error handling

- Event lạ/không nhận dạng → bỏ qua (forward-compatible)
- `tool_call` không bao giờ nhận `tool_result` (worker crash) → giữ trạng thái running, banner kết nối báo reconnect
- Abort giữa chừng → giữ partial text block
- Gap seq lớn sau reconnect → follow-stream backoff hiện có đã re-drain từ durable log

## Testing

- `npm test` (vitest, node env): reducer unit tests — mỗi event type, chuỗi thực tế (token→tool_call→tool_result→message_done), tính chất live≡replay, hydration từ persisted
- Gates: `npm run typecheck && npm run lint && npm run build && npm test`

## Ngoài phạm vi

Không đổi wire format, không thêm endpoint backend, không đụng workflow/workflow-run UI.
