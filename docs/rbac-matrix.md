# RBAC Matrix — Role × Chức năng × UI Visibility

> Tham chiếu phân quyền và kiến trúc Multi-tenant của OpenAgent. Nguồn sự thật:
> `backend/app/core/authz/policy.py` (API permissions),
> `frontend/components/layout/navigation.ts` (UI mapping),
> `backend/app/api/v1/routes/*` (route enforcement).
> Cập nhật: 2026-08-26 (Ultra-clean Persona Navigation & Multi-tenant RAG Isolation).

---

## 1. Định nghĩa 4 Vai trò (Role Personas)

| Role | Đối tượng | Nhiệm vụ cốt lõi | Cách cấp quyền |
|---|---|---|---|
| `platform_admin` | **Platform Super Admin** | **Break-glass, gần như chỉ đọc**: quản lý danh sách Tổ chức (Tenants), tạo Org, gán `org_admin` ban đầu, kích hoạt/khóa Org. Không quản lý Providers hay Logs của Org. Ngoại lệ hẹp duy nhất: được `agents:run` + `tools:use:{safe,read,network}` + `approvals:manage`, nhưng chỉ áp dụng khi chat với agent có `visibility="platform_admin"` (hiện tại chỉ có Ops & Reliability Agent — agent giám sát hệ thống, chỉ báo cáo và đề xuất, không tự sửa code/config) — không mở quyền chat với agent thường của bất kỳ Org nào. | Cấu hình qua `OPENAGENT_PLATFORM_ADMIN_EMAILS` / Zitadel platform seed |
| `org_admin` (`admin`) | **Organization Administrator** | **Quản trị toàn diện công ty**: Quản lý nhân viên (`Members & Roles`), cấu hình API Keys & Models, phân bổ Quotas & Budgets, quản lý kho tri thức **Knowledge Base**, theo dõi **Usage & Audit Logs**, cấu hình hòm thư chung. | `platform_admin` mời khi tạo Org, hoặc `org_admin` khác mời |
| `operator` | **AI Engineer / Builder / Ops** | **Chế tạo & Đánh giá giải pháp AI**: Thiết kế Agent Studio & Prompts, xây dựng visual Workflows, cấu hình MCP Servers, nạp tri thức vào **Knowledge Base**, kiểm thử Sandbox, chạy Evaluations và duyệt Technical Approvals. | `org_admin` mời và phân quyền trong Org |
| `user` | **End-User / Business Worker** | **Sử dụng AI nghiệp vụ hàng ngày**: Trò chuyện với Trợ lý AI (`Chat` kèm nút đính kèm file 📎 tức thời), chạy `Run Workflow`, nhận tóm tắt từ `Smart Inbox & Rules`, tra cứu `Research Cases`. | `org_admin` mời vào Org |

---

## 2. Ma trận UI Navigation & Chức năng theo Role

Legend:
- 🟢 **UI Hiện**: Hiển thị trong sidebar của vai trò đó, tập trung đúng nghiệp vụ.
- ❌ **UI Ẩn**: Ẩn hoàn toàn khỏi sidebar (tránh bloat giao diện) và được bảo vệ ở API layer.
- 🛡️ **API Gate**: Permission tương ứng được kiểm tra qua `Depends(require_permission(...))`.

| Chức năng (Trang UI) | Route URL | Permission gate | 👑 `platform_admin` | 🏢 `org_admin` | 🛠️ `operator` | 💼 `user` |
|---|---|---|:---:|:---:|:---:|:---:|
| **Organizations** | `/organizations` | `orgs:read` + platformOnly | 🟢 Hiện | ❌ Ẩn | ❌ Ẩn | ❌ Ẩn |
| **Members & Access** | `/settings/members` | `orgs:manage` | ❌ Ẩn | 🟢 Hiện | ❌ Ẩn | ❌ Ẩn |
| **AI Providers & Models** | `/providers` | `providers:read` | ❌ Ẩn | 🟢 Hiện | ❌ Ẩn | ❌ Ẩn |
| **Models Configuration** | `/models` | `models:read` / `models:manage` | ❌ Ẩn | 🟢 Hiện | ❌ Ẩn | ❌ Ẩn |
| **Quotas & Budgets** | `/settings/quotas` | `quota:usage` / `orgs:manage` | ❌ Ẩn | 🟢 Hiện | ❌ Ẩn | ❌ Ẩn |
| **Knowledge Base (RAG)** | `/files` | `files:read` / `files:manage` | ❌ Ẩn | 🟢 Hiện | 🟢 Hiện | ❌ Ẩn |
| **Usage & Audit Logs** | `/debug` | `orgs:manage` | ❌ Ẩn | 🟢 Hiện | ❌ Ẩn | ❌ Ẩn |
| **Email Operations** | `/admin/email-intelligence` | `admin:email-intelligence` | ❌ Ẩn | 🟢 Hiện | ❌ Ẩn | ❌ Ẩn |
| **Agent Studio** | `/agents` | `agents:read` / `agents:create` | ❌ Ẩn | ❌ Ẩn | 🟢 Hiện | ❌ Ẩn |
| **Workflow Builder** | `/workflows` | `workflows:read` / `workflows:create` | ❌ Ẩn | ❌ Ẩn | 🟢 Hiện | ❌ Ẩn |
| **MCP & Tools** | `/mcp` | `mcp:read` / `mcp:manage` | ❌ Ẩn | ❌ Ẩn | 🟢 Hiện | ❌ Ẩn |
| **Workspace & Sandbox** | `/workspace` | `files:read` / `files:write` | ❌ Ẩn | ❌ Ẩn | 🟢 Hiện | ❌ Ẩn |
| **Evaluations** | `/evaluations` | `evaluations:read` | ❌ Ẩn | ❌ Ẩn | 🟢 Hiện | ❌ Ẩn |
| **Technical Approvals** | `/approvals` | `approvals:read` / `approvals:manage` | ❌ Ẩn | ❌ Ẩn | 🟢 Hiện | ❌ Ẩn |
| **Chat Assistant** *(📎 đính kèm)* | `/chat` | `agents:run` | 🟡 Chỉ Ops Agent¹ | ❌ Ẩn | ❌ Ẩn | 🟢 Hiện |
| **Run Workflow** | `/run-workflow` | `workflows:run` | ❌ Ẩn | ❌ Ẩn | ❌ Ẩn | 🟢 Hiện |
| **Smart Inbox & Rules** | `/email-intelligence` | `ci:personal:manage` | ❌ Ẩn | ❌ Ẩn | ❌ Ẩn | 🟢 Hiện |
| **Automations Catalog** | `/automations` | `workflows:read` | ❌ Ẩn | ❌ Ẩn | ❌ Ẩn | 🟢 Hiện |
| **Research Cases** | `/customer-intelligence` | `ci:read` | ❌ Ẩn | ❌ Ẩn | ❌ Ẩn | 🟢 Hiện |
| **My Approvals & Quota** | `/approvals` | `approvals:read` / `quota:usage` | ❌ Ẩn | ❌ Ẩn | ❌ Ẩn | 🟢 Hiện |

¹ `platform_admin` không thấy `/chat` như một trang chung. Chỉ khi Org đã sync agent hệ thống **Ops & Reliability Agent** (`visibility="platform_admin"`), `platform_admin` mới chat được — và chỉ với đúng agent đó, không phải agent nào khác của Org. Agent này chỉ giám sát/báo cáo (Langfuse traces, task/approval health), không có tool nào tự sửa code hay cấu hình.

---

## 3. Kiến trúc Xử lý File & Phân tầng Vector Database (RAG Multi-tenancy)

Hệ thống phân định rạch ròi 2 cơ chế xử lý file:

1. **File Đính kèm Hội thoại (`user` — Session-Scoped Ephemeral File)**:
   - User bấm nút 📎 đính kèm tài liệu trực tiếp trong khung chat (`/chat`).
   - File được upload tạm vào Object Storage và gán `session_id`.
   - Parser trích xuất nội dung text và nạp trực tiếp vào ngữ cảnh (Context Window) của phiên chat để Agent đọc và xử lý tức thời.
   - **Tuyệt đối không nhúng vector vào Qdrant** (tránh tốn chi phí embedding và làm rác Vector DB chung của công ty).
   - User không cần trang quản lý file riêng trên sidebar.

2. **Kho Tri thức Công ty (`org_admin` & `operator` — Knowledge Base & Long-term RAG)**:
   - Tài liệu quy chuẩn của tổ chức được upload tại trang **Knowledge Base** (`/files`).
   - Bấm **"Ingest into RAG"** để cắt chunk, tính toán Embedding Vector và lưu trữ vĩnh viễn trong **Qdrant (Vector DB)**.
   - **Phân tầng Tenant 3 lớp trong Vector DB**:
     - *Lớp 1 (`org_id` Isolation)*: Mọi chunk vector mang metadata `payload.org_id = "{org_id}"`. Khi tìm kiếm tương đồng (Similarity Search), hệ thống luôn tự động chèn filter cứng theo `org_id`.
     - *Lớp 2 (Scope & Visibility)*: `visibility = "organization"` cho phép mọi Agent/User trong Org tra cứu tri thức chung.
     - *Lớp 3 (Storage Quota)*: Giới hạn tổng dung lượng lưu trữ theo từng Org (`max_storage_bytes`).

---

## 4. Cơ chế Khởi tạo & Vận hành Multi-tenant

1. **Bootstrap Platform Super Admin**:
   - Biến môi trường `OPENAGENT_PLATFORM_ADMIN_EMAILS` lưu danh sách email của `platform_admin`.
   - Khi đăng nhập lần đầu qua Zitadel SSO, backend tự động bootstrap `Organization(slug="platform")` và gán quyền `Role.platform_admin`.
2. **Khởi tạo Organization & Bổ nhiệm `org_admin`**:
   - `platform_admin` gọi `POST /api/orgs` (hoặc qua UI `/organizations`), điền tên Org và chỉ định `admin_email` ban đầu.
   - Bản ghi `Membership(role=Role.org_admin, provisioning_source="invite")` được tạo ra cho người được chỉ định.
3. **Phân quyền nội bộ Organization**:
   - `org_admin` sử dụng trang **Members** (`/settings/members` hoặc `POST /api/orgs/{id}/members`) để mời:
     - `org_admin`: Đồng quản trị viên.
     - `operator`: Kỹ sư AI phát triển Agent & Workflow.
     - `user`: Nhân viên sử dụng AI nghiệp vụ hàng ngày.
4. **Bảo mật Fail-Closed**:
   - Người dùng chưa được mời vào bất kỳ Org nào khi đăng nhập sẽ nhận mã lỗi `403 ACCOUNT_NOT_PROVISIONED`.
   - Khi frontend chưa load xong thông tin profile `/api/auth/me`, role mặc định luôn là `user` (tránh flash UI admin).

---

## 5. Guard bảo vệ xóa thành viên (Member Protection Guards)

Endpoint `DELETE /api/orgs/{id}/members/{user_id}` áp dụng các guard bảo vệ nghiêm ngặt:
1. Target có role `platform_admin` → Từ chối `403 FORBIDDEN`.
2. Tự xóa chính mình → Từ chối `400 BAD REQUEST`.
3. Target là `org_admin` cuối cùng còn active trong tổ chức → Từ chối `400 BAD REQUEST` (ngăn chặn tình trạng Org mồ côi không có người quản trị).
