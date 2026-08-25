# RBAC Matrix — Role × Chức năng × UI Visibility

> Tham chiếu phân quyền và kiến trúc Multi-tenant của OpenAgent. Nguồn sự thật:
> `backend/app/core/authz/policy.py` (API permissions),
> `frontend/components/layout/navigation.ts` (UI mapping),
> `backend/app/api/v1/routes/*` (route enforcement).
> Cập nhật: 2026-08-25 (Streamlined Persona Navigation).

---

## 1. Định nghĩa 4 Vai trò (Role Personas)

| Role | Đối tượng | Nhiệm vụ cốt lõi | Cách cấp quyền |
|---|---|---|---|
| `platform_admin` | **Platform Ops / Super Admin** | Quản lý danh sách Tổ chức (Tenants), Platform AI Gateway, Global Quota, System Health & Audit. Không tham gia chat/inbox nghiệp vụ. | Cấu hình qua `OPENAGENT_PLATFORM_ADMIN_EMAILS` / Zitadel platform org seed |
| `org_admin` (`admin`) | **Organization Administrator** | Quản lý nhân viên công ty (`Members & Roles`), cấu hình API Keys / Models của Org, phân bổ Quotas & Budgets, quản lý mailboxes dùng chung và Audit log của Org. | `platform_admin` mời khi tạo Org, hoặc `org_admin` khác mời đồng quản trị |
| `operator` | **AI Engineer / Builder / Ops** | Thiết kế Agent Studio & Prompts, xây dựng visual Workflows, cấu hình MCP Servers, Evaluations (benchmark prompt/model), Sandbox testing, duyệt Technical Approvals. | `org_admin` mời và phân quyền trong Org |
| `user` | **End-User / Business Worker** | Trò chuyện với Trợ lý AI (`Chat`), chạy Workflows nghiệp vụ (`Run Workflow`), sử dụng Smart Inbox & Automations, tải tài liệu cá nhân (`Files`), duyệt Personal Approvals & xem Quota cá nhân. | `org_admin` mời vào Org |

---

## 2. Ma trận UI Navigation & Chức năng theo Role

Legend:
- 🟢 **UI Hiện**: Hiển thị trong sidebar của vai trò đó, tập trung đúng nghiệp vụ.
- ❌ **UI Ẩn**: Ẩn hoàn toàn khỏi sidebar (tránh bloat giao diện) và được bảo vệ ở API layer.
- 🛡️ **API Gate**: Permission tương ứng được kiểm tra qua `Depends(require_permission(...))`.

| Chức năng (Trang UI) | Route URL | Permission gate | 👑 `platform_admin` | 🏢 `org_admin` | 🛠️ `operator` | 💼 `user` |
|---|---|---|:---:|:---:|:---:|:---:|
| **Platform Dashboard** | `/` | — | 🟢 Hiện | ❌ Ẩn | ❌ Ẩn | ❌ Ẩn |
| **Organizations** | `/organizations` | `orgs:read` + platformOnly | 🟢 Hiện | ❌ Ẩn | ❌ Ẩn | ❌ Ẩn |
| **Global Providers** | `/providers` | `providers:read` | 🟢 Hiện | ❌ Ẩn | ❌ Ẩn | ❌ Ẩn |
| **System Debug & Logs** | `/debug` | `orgs:manage` | 🟢 Hiện | ❌ Ẩn | ❌ Ẩn | ❌ Ẩn |
| **Org Dashboard** | `/` | — | ❌ Ẩn | 🟢 Hiện | ❌ Ẩn | ❌ Ẩn |
| **Members & Access** | `/settings/members` | `orgs:manage` | ❌ Ẩn | 🟢 Hiện | ❌ Ẩn | ❌ Ẩn |
| **Org AI Providers** | `/providers` | `providers:read` | ❌ Ẩn | 🟢 Hiện | ❌ Ẩn | ❌ Ẩn |
| **Models Configuration** | `/models` | `models:read` / `models:manage` | ❌ Ẩn | 🟢 Hiện | ❌ Ẩn | ❌ Ẩn |
| **Quotas & Budgets** | `/settings/quotas` | `quota:usage` / `orgs:manage` | ❌ Ẩn | 🟢 Hiện | ❌ Ẩn | ❌ Ẩn |
| **Email Operations** | `/admin/email-intelligence` | `admin:email-intelligence` | ❌ Ẩn | 🟢 Hiện | ❌ Ẩn | ❌ Ẩn |
| **Org Debug & Logs** | `/debug` | `orgs:manage` | ❌ Ẩn | 🟢 Hiện | ❌ Ẩn | ❌ Ẩn |
| **Operator Dashboard** | `/` | — | ❌ Ẩn | ❌ Ẩn | 🟢 Hiện | ❌ Ẩn |
| **Agent Studio** | `/agents` | `agents:read` / `agents:create` | ❌ Ẩn | ❌ Ẩn | 🟢 Hiện | ❌ Ẩn |
| **Workflow Builder** | `/workflows` | `workflows:read` / `workflows:create` | ❌ Ẩn | ❌ Ẩn | 🟢 Hiện | ❌ Ẩn |
| **MCP Servers** | `/mcp` | `mcp:read` / `mcp:manage` | ❌ Ẩn | ❌ Ẩn | 🟢 Hiện | ❌ Ẩn |
| **Workspace & Sandbox** | `/workspace` | `files:read` / `files:write` | ❌ Ẩn | ❌ Ẩn | 🟢 Hiện | ❌ Ẩn |
| **Evaluations** | `/evaluations` | `evaluations:read` | ❌ Ẩn | ❌ Ẩn | 🟢 Hiện | ❌ Ẩn |
| **Technical Approvals** | `/approvals` | `approvals:read` / `approvals:manage` | ❌ Ẩn | ❌ Ẩn | 🟢 Hiện | ❌ Ẩn |
| **Models Explorer** | `/models` | `models:read` | ❌ Ẩn | ❌ Ẩn | 🟢 Hiện | ❌ Ẩn |
| **Chat** | `/chat` | `agents:run` | ❌ Ẩn | ❌ Ẩn | ❌ Ẩn | 🟢 Hiện |
| **Run Workflow** | `/run-workflow` | `workflows:run` | ❌ Ẩn | ❌ Ẩn | ❌ Ẩn | 🟢 Hiện |
| **Smart Inbox** | `/email-intelligence` | `ci:personal:manage` | ❌ Ẩn | ❌ Ẩn | ❌ Ẩn | 🟢 Hiện |
| **Automations Catalog** | `/automations` | `workflows:read` | ❌ Ẩn | ❌ Ẩn | ❌ Ẩn | 🟢 Hiện |
| **Automation Rules** | `/email-intelligence/rules` | `ci:personal:manage` | ❌ Ẩn | ❌ Ẩn | ❌ Ẩn | 🟢 Hiện |
| **Research Cases** | `/customer-intelligence` | `ci:read` | ❌ Ẩn | ❌ Ẩn | ❌ Ẩn | 🟢 Hiện |
| **Integrations (Personal)** | `/integrations` | `ci:personal:manage` | ❌ Ẩn | ❌ Ẩn | ❌ Ẩn | 🟢 Hiện |
| **My Files** | `/files` | `files:read` / `files:write` | ❌ Ẩn | ❌ Ẩn | ❌ Ẩn | 🟢 Hiện |
| **My Approvals** | `/approvals` | `approvals:read` | ❌ Ẩn | ❌ Ẩn | ❌ Ẩn | 🟢 Hiện |
| **My Quota** | `/settings/quotas` | `quota:usage` | ❌ Ẩn | ❌ Ẩn | ❌ Ẩn | 🟢 Hiện |

---

## 3. Cơ chế Khởi tạo & Vận hành Multi-tenant

1. **Bootstrap Platform Super Admin**:
   - Biến môi trường `OPENAGENT_PLATFORM_ADMIN_EMAILS` lưu danh sách email của `platform_admin`.
   - Khi đăng nhập lần đầu qua Zitadel SSO, backend tự động bootstrap `Organization(slug="platform")` và gán quyền `Role.platform_admin`.
2. **Khởi tạo Organization & Bổ nhiệm `org_admin`**:
   - `platform_admin` gọi `POST /api/orgs` (hoặc qua UI `/organizations`), điền tên Org và chỉ định người phụ trách.
   - Bản ghi `Membership(role=Role.org_admin)` được tạo ra cho người được chỉ định.
3. **Phân quyền nội bộ Organization**:
   - `org_admin` sử dụng trang **Members** (`/settings/members` hoặc `POST /api/orgs/{id}/members`) để mời:
     - `org_admin`: Đồng quản trị viên.
     - `operator`: Kỹ sư AI phát triển Agent & Workflow.
     - `user`: Nhân viên sử dụng AI nghiệp vụ hàng ngày.
4. **Bảo mật Fail-Closed**:
   - Người dùng chưa được mời vào bất kỳ Org nào khi đăng nhập sẽ nhận mã lỗi `403 ACCOUNT_NOT_PROVISIONED`.
   - Khi frontend chưa load xong thông tin profile `/api/auth/me`, role mặc định luôn là `user` (tránh flash UI admin).

---

## 4. Guard bảo vệ xóa thành viên (Member Protection Guards)

Endpoint `DELETE /api/orgs/{id}/members/{user_id}` áp dụng các guard bảo vệ nghiêm ngặt:
1. Target có role `platform_admin` → Từ chối `403 FORBIDDEN`.
2. Tự xóa chính mình → Từ chối `400 BAD REQUEST`.
3. Target là `org_admin` cuối cùng còn active trong tổ chức → Từ chối `400 BAD REQUEST` (ngăn chặn tình trạng Org mồ côi không có người quản trị).
