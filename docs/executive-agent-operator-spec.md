# Executive Agent Operator (Chief of Staff) System Specification

> **Tài liệu đặc tả kỹ thuật & kiến trúc trải nghiệm người dùng (UX/UI Spec)** cho Trung tâm Điều hành Agent Cá nhân (Personal AI Operator) trên nền tảng **OpenAgent OS**.

---

## 1. Tầm nhìn & Mục tiêu (Vision & Objectives)

### 1.1 Vấn đề hiện tại
- Phần lớn nền tảng AI Agent truyền thống chỉ hiển thị con Agent dưới dạng một **hộp chat thụ động (Passive Chatbox)** hoặc một **form kích hoạt DAG thủ công**.
- Trong khi đó, người dùng thực tế không muốn phải bấm chạy DAG hay nhập liệu JSON hàng ngày. Hệ thống đã có sẵn các **Workflows tự động chạy ngầm (Group 1: Event-driven Gmail/Customer Triage; Group 2: Scheduled Cron Morning Command, Meeting Prep, Follow-up Radar)**.
- Người dùng cần một **Executive Chief of Staff (Trợ lý điều hành cá nhân)** tổng hợp toàn bộ hoạt động ngầm, chủ động báo cáo các insight giá trị cao, và đóng vai trò là **Human-in-the-loop Gatekeeper** để người dùng phê duyệt các hành động có tính rủi ro (gửi email, tạo lịch họp, xuất dữ liệu) trước khi thực thi.

### 1.2 Mục tiêu cốt lõi
1. **Nâng tầm trải nghiệm thị giác (Living Cybernetic AI)**: Biến con Robot 3D thành một thực thể sống động, có tư duy bối cảnh (Ambient Cognition), có bong bóng suy nghĩ nổi (Thought Bubble) và khả năng kéo/thả tự do với hít nam châm (Magnetic Docking).
2. **Minh bạch hóa quá trình suy luận (Reasoning Transparency)**: Không chỉ hiển thị kết quả, Agent đưa ra quy trình 3 bước (*Trích xuất* ➔ *Đối chiếu chính sách* ➔ *Đề xuất*) kèm **Confidence Score (Độ tin cậy %)** và **Thời gian tiết kiệm**.
3. **Khả năng mở rộng đa mục (Multi-Item Scalability)**: Khi có nhiều yêu cầu duyệt (3-5+ approvals), nhiều email (6-20+ mails), nhiều báo cáo; giao diện vẫn giữ kích thước chuẩn mực nhờ **3D Stacked Carousel**, **Segmented Capsule Tabs** và **Micro-Expand Accordions**.
4. **Bảo tồn 100% các trang chuyên sâu (Zero Destructive Refactor)**: Toàn bộ 17 routes cốt lõi của hệ thống (`/chat`, `/approvals`, `/email-intelligence`, `/customer-intelligence`, `/workflows`, `/models`, `/providers`, `/quotas`...) được giữ nguyên vẹn. Agent đóng vai trò là lớp điều hành nhanh (Quick Operator) kết nối mượt mà tới các trang chuyên sâu.

---

## 2. Kiến trúc Trải nghiệm Người dùng (UX/UI Architecture)

### 2.1 Thành phần Tương tác 3D Companion
- **Thực thể 3D (`model-viewer`)**: Model robot dịch vụ với hiệu ứng xoay đầu nhìn theo chuột (`head look-at loop`), ánh sáng HUD Telemetry (`COGNITION // 7 ROUTINES`), và vòng hào quang thở nhẹ (`Halo ring animation`).
- **Bong bóng tư duy nổi (Living Thought Bubble)**:
  - Nằm lơ lửng phía trên đầu robot (`top: -34px`).
  - Hiển thị tóm tắt sự kiện khẩn cấp nhất: `✨ Acme Corp: Đồng ý 120 seats (+140% MRR) · Cần duyệt →`.
  - Có hiệu ứng trôi nổi êm ái (`float-bubble`) và đèn tín hiệu nhấp nháy (`pulse-ring`). Click vào bong bóng sẽ mở trực tiếp bảng điều hành.
- **Kéo & Thả tự do với Vùng Hít Nam Châm (Magnetic Dock Zones)**:
  - Vùng 1: `Dock Trung tâm` (`#dockCenter` - `calc(50% + 180px), 50%`).
  - Vùng 2: `Dock Góc phải dưới` (`#dockBottomRight` - `right: 28px, bottom: 24px`).
  - Vùng 3: `Dock Cạnh bảng tin` (`#dockLeftRail` - `left: 260px, top: 140px`).
  - Khi người dùng kéo robot gần vùng nào (< 90px), robot tự động hít vào dock với hiệu ứng lò xo vật lý (`var(--ease-spring)`).

### 2.2 Bảng Điều hành Thông minh (Smart Command Surface)
- **Thiết kế Kính Mờ Siêu Thực (Deep Frosted Glassmorphism)**:
  - Nền đen sâu `rgba(12, 12, 16, 0.96)`, hiệu ứng mờ `backdrop-filter: blur(32px)`.
  - Viền 1px titan phản xạ ánh sáng `rgba(255, 255, 255, 0.14)`.
- **Tự động lật và Ôm gọn Màn hình (Smart Clamping & Auto-Flip)**:
  - Nếu khoảng cách từ robot xuống đáy màn hình không đủ hiển thị popup, popup tự động lật lên phía trên robot (`commandSurface.classList.add('above')`).
  - Popup luôn giữ khoảng cách an toàn tối thiểu `16px` với tất cả các cạnh màn hình.
  - Mũi tên chỉ báo (`#cmdArrow`) tự động dịch chuyển theo trục X (`--arrow-x`) khớp chính xác với tâm của robot.

---

## 3. Khả năng Mở rộng Đa mục (Multi-Item Scalability)

Khi có số lượng lớn dữ liệu dồn dập, Agent áp dụng 4 tầng phân cấp xử lý:

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│  [Header]: 🤖 OpenAgent Operator          [⚡ Duyệt: 3] [✉ Mail: 6] [📋 Báo cáo: 4]
├──────────────────────────────────────────────────────────────────────────────┤
│  [TAB 1: 3D Stack Carousel]                                                  │
│  ◀ [ 1 / 3 ] ▶  ⚡ Sarah Chen (Acme Corp) · HIGH RISK · 98% Confidence       │
│  • 01/ TRÍCH XUẤT: Email chốt mở rộng 120 seats mốc ngày 01/10/2026          │
│  • 02/ CHÍNH SÁCH: Hợp lệ theo biểu giá Q3 · Đối chiếu Customer Intelligence │
│  • 03/ ĐỀ XUẤT:    Tự động soạn Gmail API · Cần 1 chữ ký của bạn            │
│  [ ✨ Duyệt mục này ]   [ ✏ Xem & Sửa ]   [ Bỏ qua → ]                       │
│  ──────────────────────────────────────────────────────────────────────────  │
│  ✨ [ Duyệt nhanh tất cả 3 hành động an toàn ] (Batch Approve)               │
├──────────────────────────────────────────────────────────────────────────────┤
│  [TAB 2 & 3: Micro-Expand Accordions]                                        │
│  ▶ ✉ Sarah Chen: Hợp đồng 120 seats ──────────────────────── [8 phút trước]  │
│  ▶ 📅 David Kim: Xác nhận họp 14:00 (Dossier 5 trang) ────── [35 phút trước] │
│  ▶ 📁 Marcus Vance: Yêu cầu xuất Drive Security Whitepaper ─ [1 giờ trước]   │
├──────────────────────────────────────────────────────────────────────────────┤
│  [Chỉ đạo]: [ Giao việc tự nhiên cho Agent...                      ] [Chỉ đạo]
│  [Escalation]: Xem toàn bộ danh sách trong Approvals Queue (/approvals) →   │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 3.1 Thẻ Phê duyệt Xếp tầng Carousel (`1 of N`) & Batch 1-Click
- Hỗ trợ duyệt từng thẻ theo dạng Carousel: `[◀] [ 1 / 3 ] [▶]`.
- Nút **`[✨ Duyệt nhanh tất cả 3 hành động an toàn]`**: Kích hoạt gửi API batch-approve, giải phóng toàn bộ hàng đợi trong 1 thao tác duy nhất.

### 3.2 Bộ 3 Tab Capsule Phân loại
- `⚡ Phê duyệt (count)`: Quản lý các hành động có rủi ro (`HIGH RISK`, `STANDARD`).
- `✉ Email Triage (count)`: Danh sách các email đã được AI đọc và phân loại theo intent.
- `📋 Báo cáo (count)`: Tổng hợp bản tin ngày từ Morning Command Center, Dossier đối tác, Follow-up Radar.

### 3.3 Danh sách Thu gọn Micro-Expand (Accordion 1-Dòng)
- Mặc định mỗi thông báo/báo cáo chỉ chiếm 1 dòng thanh lịch.
- Click vào dòng sẽ bung mở chi tiết reasoning và nút hành động nhanh.

### 3.4 Điều hướng Chuyên sâu (Deep-Link Escalation)
- Cuối mỗi tab luôn có liên kết đưa người dùng đến trang quản trị toàn màn hình tương ứng khi cần xử lý dữ liệu lớn (50+ mục).

---

## 4. Đặc tả Hợp đồng Dữ liệu & API (Data Contracts)

### 4.1 Schema Dữ liệu Phê duyệt (Approval Item)
```typescript
interface OperatorApprovalItem {
  id: string;
  workflow_run_id: string;
  title: string;
  risk_level: 'HIGH_RISK' | 'STANDARD' | 'LOW';
  confidence_score: number; // 0.0 - 1.0 (ví dụ: 0.98 -> 98%)
  time_saved_minutes: number;
  reasoning_steps: Array<{
    step_number: string; // "01 / TRÍCH XUẤT", "02 / CHÍNH SÁCH", "03 / ĐỀ XUẤT"
    description: string;
  }>;
  action_payload: {
    service: 'gmail' | 'calendar' | 'drive';
    operation: string; // e.g. "send_message", "create_event"
    parameters: Record<string, any>;
  };
  created_at: string;
  expires_at: string;
}
```

### 4.2 Schema Dữ liệu Email Triage Notification
```typescript
interface OperatorEmailTriageItem {
  id: string;
  sender_name: string;
  sender_email: string;
  subject: string;
  extracted_summary: string;
  category: 'CONTRACT_UPDATE' | 'CALENDAR_INVITE' | 'DRIVE_EXPORT' | 'GENERAL';
  urgency: 'urgent' | 'warning' | 'normal';
  received_at: string;
  associated_approval_id?: string;
}
```

### 4.3 Schema Dữ liệu Báo cáo Điều hành (Executive Briefing)
```typescript
interface OperatorBriefingItem {
  id: string;
  source_routine: 'morning-command-center' | 'customer-intelligence' | 'follow-up-radar' | 'weekly-review';
  title: string;
  highlights: string[];
  confidence_score?: number;
  dossier_url?: string;
  created_at: string;
}
```

### 4.4 Endpoints API Phục vụ Operator
| Phương thức | Endpoint | Mô tả |
|---|---|---|
| `GET` | `/api/v1/operator/summary` | Lấy toàn bộ trạng thái tổng hợp (3 counts, carousel items, micro-lists). |
| `POST` | `/api/v1/approvals/{id}/decide` | Phê duyệt hoặc từ chối 1 hành động (`decision: "approved" \| "rejected"`). |
| `POST` | `/api/v1/approvals/batch-decide` | Phê duyệt hàng loạt các action hợp lệ trong 1 request. |
| `POST` | `/api/v1/operator/direction` | Gửi chỉ đạo ngôn ngữ tự nhiên từ ô input tới Orchestrator. |

---

## 5. Kế hoạch Triển khai Mã nguồn (Implementation Roadmap)

1. **Giai đoạn 1: Chuẩn bị Worktree Git (Theo `AGENTS.md`)**:
   - Tạo branch và worktree: `feat/executive-agent-operator`.
2. **Giai đoạn 2: Xây dựng Component Frontend (Next.js React)**:
   - `frontend/components/operator/companion-3d.tsx`: Module Robot 3D, Thought Bubble, Drag physics và Magnetic Docking.
   - `frontend/components/operator/operator-surface.tsx`: Module Command Surface, Smart Clamping, Auto-Flip và Capsule Tabs.
   - `frontend/components/operator/approval-carousel.tsx`: 3D Stack Carousel và Batch Approve.
   - `frontend/components/operator/micro-accordion-list.tsx`: Accordion thu gọn cho Email Triage & Báo cáo.
3. **Giai đoạn 3: Tích hợp API Backend & Hook React Query**:
   - Viết hook `useOperatorState()` kết nối với API backend và WebSocket/SSE để nhận thông báo thời gian thực khi có email mới.
4. **Giai đoạn 4: Kiểm thử & Đảm bảo Chất lượng (QA & E2E)**:
   - Chạy `npm run typecheck`, `npm run build`, và kiểm tra phản hồi trên mọi kích thước màn hình.
