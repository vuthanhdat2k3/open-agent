# Companion Operator Agent v2 — Từ HUD thụ động sang Agent điều khiển ứng dụng

> Tài liệu thiết kế kỹ thuật. Kế thừa và mở rộng [`executive-agent-operator-spec.md`](./executive-agent-operator-spec.md) (v1).
> Trạng thái: **Đề xuất — chờ duyệt**. Chưa có code nào được viết theo tài liệu này.

---

## 1. Bối cảnh

### 1.1 v1 đã làm được gì (đang chạy production)

`frontend/components/operator/companion-3d.tsx` (502 dòng) hiện là một **HUD thụ động**:

| Khả năng hiện có | Nguồn dữ liệu |
|---|---|
| Avatar GLB kéo–thả, hít dock nam châm, bong bóng tư duy | `<model-viewer>`, `lib/operator/companion-config` |
| Hiển thị approvals đang chờ | `useApprovals` |
| Hiển thị notification Customer Intelligence | `useCustomerIntelligenceNotifications` |
| Hiển thị case CI, report workflow-run | `useCustomerIntelligenceCases`, `useNotifications` |
| Đếm routines đang bật | `getWorkflowInstallations` |
| **Hành động duy nhất**: duyệt / từ chối approval | `useDecideApproval` |

Render tại `components/layout/app-shell.tsx:77`, chỉ cho end-user (`isEndUserFlag`).

### 1.2 Giới hạn cốt lõi

Con bot **đọc được nhưng không làm được**. Mọi thứ nó biết đều là dữ liệu đẩy tới nó; nó không có kênh nào để:
- trò chuyện (không có khung chat, không nối vào agent loop),
- thao tác trên chính giao diện người dùng đang mở,
- hiểu người dùng **đang xem cái gì**.

### 1.3 Điều bất ngờ: hạ tầng đã sẵn 90%

Ba hook có sẵn trong backend biến việc này từ "viết mới" thành "nối dây":

| Hook | Vị trí | Vai trò trong v2 |
|---|---|---|
| `ToolContext.emit` | `backend/app/core/tools/types.py` | Tool đang chạy **đẩy sự kiện realtime** về client giữa chừng |
| `ChatRunEvent` (append-only, replay được) | `backend/app/models/chat_run_event.py` | Sự kiện `ui_action` tới browser và **sống sót sau F5** |
| `ToolSpec.risk_tier` + `requires_approval` | `backend/app/core/tools/types.py`, `core/guardrails/approval.py` | Chặn hành động rủi ro bằng **cơ chế duyệt sẵn có** |

Kênh SSE `GET /api/chat/runs/{run_id}/events?follow=true&after_seq=N` đã hoạt động ổn định (đã kiểm chứng live).

**Mảnh duy nhất còn thiếu**: một cầu nối cho phép tool chạy *trên trình duyệt* thay vì trên server.

---

## 2. Mục tiêu

### 2.1 Trong phạm vi
1. Con bot trở thành **giao diện hội thoại** dùng lại agent loop + SSE sẵn có.
2. Agent **điều khiển được ứng dụng**: điều hướng, lọc, mở panel, điền form, đọc ngữ cảnh màn hình.
3. Agent **biết người dùng đang xem gì** để trả lời/thao tác theo ngữ cảnh.
4. Mọi hành động ghi đều đi qua **approval gate sẵn có**.
5. Chuyển chuỗi thao tác đã làm thành **workflow tái sử dụng**.

### 2.2 Ngoài phạm vi (v2 không làm)
- Không thay thế trang `/chat` chuyên sâu — bot là lớp điều hành nhanh (giữ nguyên cam kết "Zero Destructive Refactor" của v1).
- Không cho agent điều khiển DOM tùy ý (xem §7.2).
- Không đổi schema DB (dùng lại `chat_run_events`).
- Không làm mobile-native, không thêm ngôn ngữ ngoài vi/en đã có.

---

## 3. Kiến trúc: Client Tool Bridge

Ý tưởng: tool `ui.*` **không thực thi trên server**. `run()` phát một sự kiện rồi *chờ* trình duyệt làm và báo kết quả về.

```
                  ┌──────────────────────── backend ────────────────────────┐
   người dùng     │                                                          │
   gõ/nói ──POST /api/chat──►  agent loop  ──gọi tool ui.navigate──►  ui.*   │
                  │                ▲                                   │     │
                  │                │                        ctx.emit({event: │
                  │                │                         "ui_action"})   │
                  │                │                                   │     │
                  │        chờ kết quả (Redis pub/sub, timeout)        ▼     │
                  │                │                            ChatRunEvent │
                  └────────────────┼──────────────────────────────────┬──────┘
                                   │                                  │ SSE
                       POST /api/chat/runs/{id}/ui-result             ▼
                                   │                         ┌────────────────┐
                                   └─────────────────────────│  Companion 3D  │
                                          báo kết quả        │  (trình duyệt) │
                                                             │  thực thi hành │
                                                             │  động trên UI  │
                                                             └────────────────┘
```

### 3.1 Trình tự một lượt

1. Người dùng: *"Mở báo cáo tuần trước, lọc các run lỗi"*.
2. `POST /api/chat` (đã có) → agent loop chạy.
3. Agent gọi `ui.navigate({route: "/reports"})`.
4. `run()` sinh `call_id`, `await ctx.emit({"event": "ui_action", "data": {...}})`, rồi chờ.
5. Sự kiện được ghi vào `chat_run_events` và đẩy qua SSE tới companion.
6. Companion tra **UI Action Registry**, thực thi (`router.push("/reports")`), chờ trang ổn định.
7. Companion `POST /api/chat/runs/{id}/ui-result` với `call_id` + kết quả.
8. Backend đánh thức `run()` đang chờ → tool trả chuỗi kết quả cho agent loop.
9. Agent gọi tiếp `ui.set_filter({status: "failed", range: "last_week"})` → lặp lại.
10. Agent kết luận bằng văn bản; companion đọc to nếu bật giọng nói.

### 3.2 Cơ chế chờ xuyên tiến trình

Chat run có thể chạy ở tiến trình **worker** trong khi POST kết quả rơi vào tiến trình **api**. Vì vậy **không dùng `asyncio.Event` trong bộ nhớ**, mà dùng Redis (đã có trong stack):

- Tool `run()`: `BLPOP openagent:ui_result:{call_id}` với timeout.
- Endpoint `ui-result`: `RPUSH` payload vào đúng key đó.
- Hết timeout → tool trả lỗi có cấu trúc (`{"ok": false, "error": "ui_timeout"}`) để agent tự xoay xở, **không treo run**.

---

## 4. Hợp đồng giao thức

### 4.1 Sự kiện `ui_action` (backend → browser)

Ghi vào `chat_run_events.event = "ui_action"` (cột `String(48)`, vừa đủ), `data`:

```json
{
  "call_id": "b1c2...",
  "tool": "ui.navigate",
  "args": { "route": "/reports" },
  "timeout_ms": 15000,
  "requires_ack": true
}
```

### 4.2 `POST /api/chat/runs/{run_id}/ui-result` (browser → backend)

```json
{
  "call_id": "b1c2...",
  "ok": true,
  "result": { "route": "/reports", "settled_ms": 420 },
  "error": null
}
```

- **Xác thực**: cookie phiên hiện hành + header `X-CSRF-Token` (bắt buộc cho method không an toàn — xem `core/auth/application_session.py::resolve_application_session`).
- **Phân quyền**: người gọi phải là chủ của `run_id` trong đúng org.
- **Idempotent**: `call_id` đã nhận kết quả thì lần POST sau trả `200` và bỏ qua.

### 4.3 An toàn khi replay (bắt buộc)

`chat_run_events` được **phát lại** khi tải lại trang. Nếu không xử lý, bot sẽ thực thi lại hành động cũ.

⇒ Companion lưu tập `call_id` đã thực thi trong `sessionStorage`; sự kiện `ui_action` có `call_id` đã nằm trong tập này thì **chỉ hiển thị lại, không thực thi**.

---

## 5. Bộ tool `ui.*`

Chỉ agent "Personal Operator" được cấp (cột `Agent.tools: list[str]`, `backend/app/models/agent.py:34`).

| Tool | Tham số | Risk tier | Cần duyệt | Ghi chú |
|---|---|---|---|---|
| `ui.read_screen` | – | `safe` | ✗ | Trả về Page Context Envelope (§6) |
| `ui.navigate` | `route`, `params?` | `safe` | ✗ | Chỉ route nằm trong allowlist |
| `ui.set_filter` | `filters{}` | `safe` | ✗ | Áp filter đã đăng ký của trang hiện tại |
| `ui.open_panel` | `panel`, `id?` | `safe` | ✗ | Mở dialog/side panel đã đăng ký |
| `ui.fill_form` | `form`, `values{}` | `write` | ✗ | Chỉ điền, **không** submit |
| `ui.submit_form` | `form`, `confirm` | `write` | ✓ | Hành động ghi thật |
| `ui.run_workflow` | `workflow_id`, `inputs{}` | `execute` | ✓ | Đi qua quota + approval sẵn có |
| `ui.export` | `target`, `format` | `write` | ✓ | Xuất dữ liệu ra ngoài |

Tool cần duyệt sẽ gọi `request_approval(...)` (`core/guardrails/approval.py:17`) với `tool_name`, `args_snapshot`, `idempotency_key` — đúng luồng approval mà con bot **đã biết hiển thị và duyệt** từ v1. Không phải viết UI duyệt mới.

---

## 6. Page Context Envelope

Companion đính kèm ngữ cảnh vào mỗi tin nhắn (và trả về khi gọi `ui.read_screen`):

```json
{
  "route": "/reports",
  "title": "Reports",
  "filters": { "status": "failed", "range": "7d" },
  "selection": { "type": "workflow_run", "id": "c876..." },
  "visible": [
    { "type": "workflow_run", "id": "c876...", "label": "News Crawl", "status": "failed" }
  ],
  "capabilities": ["ui.set_filter", "ui.open_panel:run_detail"]
}
```

Nguyên tắc: **chỉ id + nhãn đã hiển thị trên màn hình**, không bao giờ dump toàn bộ DOM hay dữ liệu nhạy cảm. Mỗi trang tự khai báo envelope của mình qua hook `usePageContext()`.

---

## 7. Guardrail & bảo mật

1. **Không điều khiển DOM tự do.** Agent chỉ gọi được các *capability đã đăng ký* trong UI Action Registry (typed, có version). Không có `ui.click(selector)` kiểu tùy ý.
2. **Allowlist route/panel/form** khai báo tại frontend; tool nhận tham số không nằm trong allowlist → trả lỗi, không thực thi.
3. **Chống prompt injection**: nội dung do agent/LLM sinh ra không bao giờ được dùng làm selector hay URL thô; chỉ khớp vào registry theo tên định danh.
4. **Approval cho mọi hành động ghi** (§5) — tái dùng gate hiện có, có audit log.
5. **Giới hạn**: tối đa N hành động UI mỗi run (đề xuất 12) để tránh vòng lặp; đếm chung với `budget_max_tool_calls`.
6. **Timeout & huỷ**: người dùng bấm "Dừng" là abort cả SSE lẫn hành động đang chờ.
7. **Đa tab**: chỉ tab đang focus thực thi. Bầu chọn qua `BroadcastChannel("openagent-ui-bridge")`; các tab khác chỉ hiển thị.
8. **Nhật ký**: mọi `ui_action` + kết quả đã nằm sẵn trong `chat_run_events` ⇒ có sẵn dấu vết kiểm toán, không cần bảng mới.

---

## 8. Thay đổi phía frontend

Tách `companion-3d.tsx` (đang gánh cả 3 vai) thành:

| Thành phần mới | Trách nhiệm |
|---|---|
| `Companion3DAvatar` | Chỉ hình ảnh: GLB, dock, animation theo trạng thái |
| `CompanionAgentProvider` | Phiên chat, SSE, hàng đợi hành động, máy trạng thái |
| `lib/operator/ui-actions.ts` | **UI Action Registry**: `Record<string, (args) => Promise<Result>>` |
| `usePageContext()` | Mỗi trang khai báo envelope §6 |
| `CompanionChatSurface` | Khung hội thoại trong bong bóng (dùng lại `streamSSEGet` sẵn có) |

Máy trạng thái điều khiển animation GLB: `idle → listening → thinking → acting → needs_approval → error`.

---

## 9. ⭐ Tính năng đột phá: Làm mẫu → Lưu thành Workflow

Sau một chuỗi thao tác thành công, bot đề nghị: *"Lưu 5 bước vừa rồi thành workflow?"*.

**Vì sao khả thi ở đây mà khó ở nơi khác**: cần đủ **cả ba** thứ mà dự án này đã có sẵn — agent loop có tool-calling, workflow engine DAG, và approval gate.

Cách chuyển đổi:
1. Trace đã có sẵn trong `chat_run_events` của run đó (mọi tool call + tham số).
2. Mỗi tool call → một node; thứ tự thực thi → cạnh tuyến tính.
3. Giá trị người dùng cung cấp → biến input của workflow (`{{input.x}}`).
4. Chuẩn hoá tham số bằng `workflow_service.strip_unknown_node_parameters` + `node_definitions` sẵn có.
5. Mở workflow canvas với DAG nháp để người dùng sửa/lưu — **không tự lưu**.

Giá trị: biến copilot dùng-một-lần thành automation tái sử dụng, kéo người dùng vào đúng tính năng lõi (workflow) mà không cần dạy họ dựng DAG thủ công.

---

## 10. Giọng nói (tuỳ chọn, rẻ)

Web Speech API — chạy **local trong trình duyệt**, không tốn token, không gửi audio ra ngoài:
- Nghe: `webkitSpeechRecognition`, `lang = vi-VN | en-US` theo `useTranslation()`.
- Nói: `speechSynthesis` đọc câu trả lời cuối (bỏ qua khối code/bảng).
- Mặc định **tắt**; bật trong `companion-config`. Chỉ nghe khi người dùng giữ nút — không nghe ngầm.

---

## 11. Kế hoạch triển khai

| Pha | Nội dung | Ước lượng | Tiêu chí nghiệm thu |
|---|---|---|---|
| **P1** | Client Tool Bridge + `ui.navigate/set_filter/open_panel/read_screen` + khung chat trong bong bóng | 2–3 ngày | Nói *"mở báo cáo tuần trước lọc run lỗi"* → điều hướng + lọc đúng, F5 không chạy lại hành động cũ |
| **P2** | Page Context Envelope cho 5 trang chính | 2 ngày | Hỏi *"cái tôi đang xem là gì"* → trả lời đúng bản ghi đang chọn |
| **P3** | Agent chủ động từ feed sẵn có + `ui.fill_form`/`submit_form` qua approval | 2 ngày | Có run lỗi → bot chủ động đề xuất, duyệt 1 chạm, có audit log |
| **P4** | Giọng nói + animation theo trạng thái | 1–2 ngày | Nói tiếng Việt điều khiển được, có phản hồi âm thanh |
| **P5** | Làm mẫu → Workflow | 3–4 ngày | Chuỗi ≥3 bước → sinh DAG nháp mở được trong canvas |

Tổng: **10–14 ngày công**. P1 là nền bắt buộc; P2–P5 độc lập nhau, chia song song được.

### Chia việc song song
- **BE**: bridge Redis + endpoint `ui-result` + đăng ký tool `ui.*` (P1, P3)
- **FE-core**: UI Action Registry + executor + replay guard (P1)
- **FE-UX**: tách component, khung chat, máy trạng thái + animation (P1, P4)
- **FE-pages**: `usePageContext()` cho từng trang (P2, làm được ngay sau khi P1 chốt interface)
- **Fullstack**: trace → DAG (P5)

---

## 12. Rủi ro & câu hỏi mở

| Rủi ro | Giảm thiểu |
|---|---|
| Agent lạm dụng hành động UI, lặp vô hạn | Giới hạn 12 hành động/run, tính chung `budget_max_tool_calls` |
| LLM chọn sai capability gây thao tác nhầm | Mọi hành động ghi phải qua approval; hành động đọc thì vô hại |
| Trang chưa khai báo `usePageContext` | Bridge trả `capabilities: []` → agent tự biết là không thao tác được, trả lời bằng văn bản |
| Người dùng đóng tab giữa chừng | Tool timeout trả lỗi có cấu trúc; run không treo |

**Câu hỏi cần chốt trước khi code:**
1. Con bot chỉ dành cho end-user như hiện tại, hay mở cho cả `operator`/`org_admin`?
2. Có cho phép agent thao tác khi người dùng **không** đang mở tab đó (chạy nền) không? (đề xuất: **không**)
3. P5 có nên tự đề xuất lưu workflow, hay chỉ khi người dùng hỏi? (đề xuất: chỉ gợi ý sau chuỗi ≥3 bước thành công)

---

## 13. Thay đổi so với v1

Tài liệu này **không phủ định** v1. Toàn bộ phần hình ảnh, docking, carousel duyệt, thang bậc hiển thị đa mục của v1 giữ nguyên. v2 chỉ bổ sung lớp **hội thoại + hành động** bên dưới lớp hình ảnh đó.
