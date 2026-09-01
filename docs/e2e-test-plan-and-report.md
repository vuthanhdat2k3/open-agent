# Kế hoạch & Báo cáo Kiểm thử Toàn diện Hệ thống OpenAgent (Comprehensive E2E Test Report)

---

## MỤC LỤC
1. [Tổng quan Kiến trúc Phân quyền (RBAC Matrix)](#1-tổng-quan-kiến-trúc-phân-quyền-rbac-matrix)
2. [Role 1: User (End-User / Business Consumer)](#2-role-1-user-end-user--business-consumer)
3. [Role 2: Operator (AI Engineer / AI Operations Stack)](#3-role-2-operator-ai-engineer--ai-operations-stack)
4. [Role 3: Org Admin (Organization Administrator)](#4-role-3-org-admin-organization-administrator)
5. [Role 4: Platform Admin (System Super Admin)](#5-role-4-platform-admin-system-super-admin)
6. [Tổng kết & Đánh giá Chung](#6-tổng-kết--đánh-giá-chung)

---

## 1. Tổng quan Kiến trúc Phân quyền (RBAC Matrix)

OpenAgent phân chia 4 vai trò rõ rệt theo ma trận phân quyền:

| Phân hệ / Tính năng | Endpoint UI | User | Operator | Org Admin | Platform Admin |
|---|---|:---:|:---:|:---:|:---:|
| **Personal Workspace** | `/`, `/chat`, `/integrations` | ✅ | ✅ | ✅ | ✅ |
| **Email & Customer Intelligence** | `/email-intelligence`, `/customer-intelligence` | ✅ | ✅ | ✅ | ✅ |
| **Trung tâm Phê duyệt** | `/approvals` | ✅ | ✅ | ✅ | ✅ |
| **Workflow Designer & Runtime** | `/workflows` | ✅ | ✅ | ✅ | ✅ |
| **AI Studio (Agents, MCP, RAG)** | `/agents`, `/providers`, `/mcp`, `/files` | ❌ (Chặn) | ✅ | ✅ | ✅ |
| **Observability (Audit, Sandbox, Evals)** | `/debug`, `/workspace`, `/evaluations` | ❌ (Chặn) | ✅ | ✅ | ✅ |
| **Administration (Members, Quotas, Gateway)** | `/settings/members`, `/settings/quotas`, `/admin/email-intelligence` | ❌ (Chặn) | ❌ (Chặn) | ✅ | ✅ |
| **Platform Governance (Multi-Tenant Orgs)** | `/organizations` | ❌ (Chặn) | ❌ (Chặn) | ❌ (Chặn) | ✅ |

---

## 2. Role 1: User (End-User / Business Consumer)

- **Tài khoản kiểm thử**: `user@protonx.com` / `Protonx@2026`
- **Mục tiêu**: Người dùng doanh nghiệp sử dụng trợ lý AI, thiết kế và kích hoạt workflow cá nhân, kết nối hộp thư, xem tình báo khách hàng và xử lý phê duyệt rủi ro.

### Test Cases & Kết quả Thực thi

| ID | Chức năng | Mô tả thực hiện | Kết quả thực tế | Trạng thái |
|---|---|---|---|:---:|
| **U-01** | **RBAC Menu Scope** | Kiểm tra Sidebar menu khi đăng nhập | Chỉ hiển thị nhóm `Workspace` (Overview, Chat, Workflows, Integrations, Email Intelligence, Customer Intelligence, Approvals). Các menu quản trị bị ẩn. | **PASS** |
| **U-02** | **Overview Dashboard** | Tải trang `/` | Hiển thị lời chào cá nhân, 12 Agent sẵn sàng, danh sách workflow và thống kê hành động chờ duyệt. | **PASS** |
| **U-03** | **Chat Assistant** | Gửi tin nhắn đến Agent | Tin nhắn được stream về mượt mà kèm khối suy luận (Thinking Reasoning). Nút "Tạo phiên mới" (New chat) hoạt động chuẩn xác chỉ với **1 click duy nhất**. | **PASS** |
| **U-04** | **Workflow Execution** | Tải mẫu Blueprint ảo & chạy | Tải mẫu `Morning Command Center` và `Meeting Preparation`. Hệ thống tự động khởi tạo DB override an toàn, chạy qua node Trigger và dừng lại an toàn khi thiếu OAuth. | **PASS** |
| **U-05** | **Integrations** | Trang kết nối `/integrations` | Hiển thị 3 cổng kết nối OAuth: Gmail, Google Calendar, Google Drive. | **PASS** |
| **U-06** | **Email Intelligence** | Hộp thư thông minh & Rules | Bộ lọc thời gian/danh mục hoạt động tốt. Tab "Quy tắc Tự động duyệt" cho phép tạo quy tắc họp với tiêu chuẩn an toàn SPF/DKIM/DMARC. | **PASS** |
| **U-07** | **Customer Intelligence** | Tra cứu doanh nghiệp | Giao diện hiển thị danh sách hồ sơ, bộ lọc thẻ/lưới và tín hiệu khách hàng trước cuộc họp. | **PASS** |
| **U-08** | **Approvals Center** | Quản lý hành động rủi ro | Xem danh sách hành động chờ duyệt (ví dụ: `delegate_to_deep_web_researcher`), mở modal giải thích lý do, nút Phê duyệt / Từ chối sẵn sàng. | **PASS** |
| **U-09** | **Profile Settings** | Trang `/settings/profile` | Hiển thị vai trò `Người dùng`, tổ chức `ProtonX`, hỗ trợ đổi mật khẩu. | **PASS** |
| **U-10** | **RBAC Security Guard** | Cố tình truy cập `/settings/members`, `/providers` | Giao diện cảnh báo quyền chỉ xem và API backend trả về 403 Forbidden, chặn thao tác trái phép. | **PASS** |
| **U-11** | **i18n Localization** | Chuyển đổi ngôn ngữ VI ↔ EN | Bản địa hóa 100% toàn bộ giao diện người dùng. | **PASS** |

---

## 3. Role 2: Operator (AI Engineer / AI Operations Stack)

- **Tài khoản kiểm thử**: `operator@protonx.com` / `Protonx@2026`
- **Mục tiêu**: Kỹ sư AI & Vận hành hệ thống quản lý danh mục Agent, kết nối Provider AI, MCP Server, Kho tri thức RAG, chạy Đánh giá benchmark, Sandbox mã nguồn và xem Audit Log.

### Test Cases & Kết quả Thực thi

| ID | Chức năng | Mô tả thực hiện | Kết quả thực tế | Trạng thái |
|---|---|---|---|:---:|
| **OP-01** | **RBAC Menu Scope** | Kiểm tra Sidebar menu | Hiển thị 2 nhóm chuyên trách: **Quy trình agentic** (`Tổng quan Studio`, `Agent`, `Nhà cung cấp`, `Workflow`, `MCP Servers`, `Kho tri thức`) và **Quản trị & kiểm toán** (`Nhật ký kiểm toán`, `Sandbox`, `Đánh giá`, `Phê duyệt`). | **PASS** |
| **OP-02** | **Studio Overview** | Tải trang `/` | Hiển thị Dashboard Kỹ sư AI: thống kê 12 Agent, 1 Orchestrator + 11 Worker, 7 Workflow, tích hợp Langfuse Active và Sandbox an toàn. | **PASS** |
| **OP-03** | **Quản lý Agent** | Trang `/agents` | Quản lý 12 Agent chuyên trách, phân tách rõ ràng Orchestrator vs Worker, xem 5 công cụ tích hợp sẵn và ủy quyền động. Tab cấu hình 3D Companion hoạt động tốt. | **PASS** |
| **OP-04** | **Quản lý AI Provider** | Trang `/providers` | Quản lý Provider Alibaba Cloud, kiểm tra kết nối API endpoint, khám phá 164 model và ma trận tầng model tier matrix. | **PASS** |
| **OP-05** | **MCP Servers** | Trang `/mcp` | Quản lý MCP Server RAG (`http://rag-service:8101/sse`) kết nối thành công, hiển thị đầy đủ 6 công cụ RAG (`rag_search`, `rag_ingest_*`, v.v.). | **PASS** |
| **OP-06** | **Kho tri thức & Sandbox** | Trang `/files` & `/workspace` | Upload tài liệu tri thức RAG và môi trường thực thi mã nguồn Sandbox an toàn. | **PASS** |
| **OP-07** | **Đánh giá & Audit Logs** | Trang `/evaluations` & `/debug` | Tạo bài test đánh giá prompt và theo dõi lịch sử truy vết cuộc gọi AI / Token consumption. | **PASS** |

---

## 4. Role 3: Org Admin (Organization Administrator)

- **Tài khoản kiểm thử**: `admin@protonx.com` / `Protonx@2026`
- **Mục tiêu**: Quản trị viên tổ chức quản lý thành viên, phân quyền vai trò (User/Operator/Admin), phân bổ hạn mức chi phí (Quotas), quản trị Email Gateway và xem báo cáo tài nguyên tiêu thụ.

### Test Cases & Kết quả Thực thi

| ID | Chức năng | Mô tả thực hiện | Kết quả thực tế | Trạng thái |
|---|---|---|---|:---:|
| **OA-01** | **RBAC Menu Scope** | Kiểm tra Sidebar menu | Hiển thị nhóm **Cài đặt hệ thống** (`Tổng quan`, `Thành viên`, `Hạn mức`, `Email Gateway`, `Nhật ký kiểm toán`). | **PASS** |
| **OA-02** | **Admin Dashboard** | Tải trang `/` | Hiển thị số lượng thành viên, hạn mức tích lũy, danh sách yêu cầu chờ duyệt và bảng chi tiết mức tiêu thụ Token theo từng Agent/Model (Deep Web Researcher, General Assistant, Qwen3.7/3.6/3.5). | **PASS** |
| **OA-03** | **Quản lý Thành viên** | Trang `/settings/members` | Hiển thị danh sách 3 thành viên (`admin`, `operator`, `user`), form thêm thành viên mới tự động đồng bộ tài khoản ZITADEL, đổi quyền vai trò qua dropdown, bảo vệ tài khoản admin chính (`Thành viên được bảo vệ`). | **PASS** |
| **OA-04** | **Quản lý Hạn mức** | Trang `/settings/quotas` | Phân bổ ngân sách chi phí hàng tháng, hạn mức token theo tháng/ngày và giới hạn số phiên chạy đồng thời. | **PASS** |
| **OA-05** | **Email Gateway Ops** | Trang `/admin/email-intelligence` | Thiết lập bộ định tuyến cổng email tập trung cấp doanh nghiệp. | **PASS** |

---

## 5. Role 4: Platform Admin (System Super Admin)

- **Tài khoản kiểm thử**: `zitadel-admin@zitadel.127.0.0.1.sslip.io` / `Protonx@2026`
- **Mục tiêu**: Quản trị viên cấp cao nhất của nền tảng quản lý danh sách Tổ chức (Tenants), tạo tổ chức mới, gán Org Admin ban đầu và giám sát sức khỏe toàn bộ 8 microservices.

### Test Cases & Kết quả Thực thi

| ID | Chức năng | Mô tả thực hiện | Kết quả thực tế | Trạng thái |
|---|---|---|---|:---:|
| **PA-01** | **RBAC Menu Scope** | Kiểm tra Sidebar menu | Hiển thị nhóm **Quản trị nền tảng** (`Tổng quan`, `Tổ chức`). | **PASS** |
| **PA-02** | **Platform Dashboard** | Tải trang `/` | Giám sát trạng thái thời gian thực của **8/8 dịch vụ cốt lõi** (`FastAPI Core API`, `PostgreSQL Database`, `Redis Broker`, `MinIO Storage`, `Docling Parser`, `Customer Intelligence MCP`, `RAG Service MCP`, `Langfuse Observability`). | **PASS** |
| **PA-03** | **Quản lý Multi-Tenancy** | Trang `/organizations` | Hiển thị danh sách tất cả các Tenant trong hệ thống (`ProtonX`, `OpenAgent Platform`), form tạo tổ chức mới kèm Org Admin ban đầu và mật khẩu khởi tạo. | **PASS** |
| **PA-04** | **Tenant Operations** | Quản trị Tenant | Hỗ trợ xem danh sách thành viên theo từng Tenant, đổi tên tổ chức và quản lý vòng đời tenant an toàn. | **PASS** |

---

## 6. Tổng kết & Đánh giá Chung

- **Tổng số Test Cases**: **26 / 26 PASSED (100%)**
- **Độ phủ phân quyền**: Đã kiểm tra đầy đủ cả **4 cấp độ Role** (`user`, `operator`, `org_admin`, `platform_admin`).
- **Khả năng tự phục hồi & toàn vẹn**:
  - Đã fix triệt để lỗi giật session/click đúp (1-click New Chat).
  - Đã fix triệt để lỗi CORS khi chạy SSE Workflow run trực tiếp.
  - Đã fix triệt để lỗi vi phạm khóa ngoại khi chạy các Blueprint Workflow ảo thông qua cơ chế Fork-on-Run / `ensure_persisted()`.
- **Tài liệu kiểm thử**: Được lưu trữ cố định tại [`docs/e2e-test-plan-and-report.md`](docs/e2e-test-plan-and-report.md).
