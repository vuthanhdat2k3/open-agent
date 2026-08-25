# RBAC Matrix — Role × Chức năng × UI Visibility

> Tham chiếu phân quyền của OpenAgent. Nguồn sự thật: `backend/app/core/authz/policy.py`
> (permissions), `frontend/components/layout/navigation.ts` (UI mapping),
> `backend/app/api/v1/routes/*` (route enforcement). Cập nhật: 2026-08-25.

## 1. Roles

| Role | Mô tả | Cách cấp |
|---|---|---|
| `platform_admin` | Quản trị toàn platform, thấy mọi org | Seed / OIDC role mapping |
| `org_admin` (`admin` legacy) | Quản trị org: hệ thống, members, cấu hình | Invite / register tạo org |
| `operator` | Vận hành: chạy và chỉnh tác phẩm, không quản trị org | Invite |
| `user` | Thành viên thường: sử dụng chat/workflow, dữ liệu cá nhân | Invite |

## 2. Ma trận chức năng × Role

Legend: ✅ full · 👁 read-only · ❌ không có quyền (UI ẩn + API 403)

| Chức năng (UI) | Permission gate | platform_admin | org_admin | operator | user |
|---|---|---|---|---|---|
| Dashboard | — | ✅ | ✅ | ✅ | ✅ |
| Chat | `agents:run` | ✅ | ✅ | ✅ | ✅ |
| Run Workflow | `workflows:run` | ✅ | ✅ | ✅ | ✅ |
| Agents (xem/chạy) | `agents:read` | ✅ | ✅ | ✅ | ✅ |
| Agents (tạo/sửa/xóa) | `agents:create/update/delete` | ✅ | ✅ | ✅ create/update/publish · ❌ delete | ❌ |
| Workflows (xem/chạy) | `workflows:read` | ✅ | ✅ | ✅ | ✅ |
| Workflows (tạo/sửa/xóa) | `workflows:create/delete` | ✅ | ✅ | ✅ | ❌ |
| Workspace + Sandbox | `files:read` | ✅ | ✅ | ✅ | ✅ |
| MCP Servers | `mcp:read` | ✅ | ✅ | ✅ | ❌ ẩn |
| Integrations (personal) | `ci:personal:manage` | ✅ | ✅ | ✅ | ✅ |
| Smart Inbox | `ci:personal:manage` | ✅ | ✅ | ✅ | ✅ |
| Automations | `workflows:read` | ✅ | ✅ | ✅ | ✅ |
| Automation Rules | `ci:personal:manage` | ✅ | ✅ | ✅ | ✅ |
| Research Cases | `ci:read` | ✅ | ✅ | ✅ | ✅ |
| Models (xem) | `models:read` | ✅ | ✅ | ✅ | ✅ |
| Models (quản lý) | `models:manage` | ✅ | ✅ | ❌ | ❌ |
| Providers | `providers:read` | ✅ | ✅ | ✅ | ❌ ẩn |
| Files | `files:read` | ✅ | ✅ | ✅ | ✅ |
| Approvals | `approvals:read` | ✅ | ✅ | ✅ | ✅ |
| Approvals (duyệt) | `approvals:manage` | ✅ | ✅ | ✅ | ❌ |
| Evaluations | `evaluations:read` | ✅ | ✅ | ✅ | ❌ ẩn |
| Quotas | `quota:usage` | ✅ | ✅ | ❌ ẩn | ✅ (usage của mình) |
| Members | `orgs:manage` | ✅ | ✅ | ❌ ẩn | ❌ ẩn |
| Debug | `orgs:manage` | ✅ | ✅ | ❌ ẩn | ❌ ẩn |
| Email Operations | `ci:organization:read` | ✅ | ✅ | ✅ | ❌ ẩn |
| Organizations | `orgs:read` + platformOnly | ✅ | ❌ ẩn | ❌ ẩn | ❌ ẩn |

## 3. Cơ chế hoạt động

1. **Backend** là nguồn sự thật: `MeResponse.permissions_by_org[org_id]` trả về bộ
   permission effective (đã resolve wildcard) cho từng org khi login.
2. **Frontend sidebar** (`app-sidebar.tsx`) filter từng nav item theo
   `item.permission` qua `hasUiPermission()` (hỗ trợ wildcard `domain:*`), cộng
   thêm cờ `platformOnly`.
3. **API enforcement** độc lập với UI: mọi route đều `Depends(require_permission(...))`
   — deep-link vào trang ẩn vẫn 403 ở tầng API, UI chỉ là lớp hiển thị.
4. Fail-closed: khi `/api/auth/me` chưa load, role mặc định là `user` (không
   flash UI admin).

## 4. Quy ước integrations (connection ownership)

- **Mailbox cá nhân** → user tự connect (scope `ci:personal:manage`); admin hệ
  thống KHÔNG connect hộ mailbox cá nhân của mình.
- **Mailbox dùng chung tổ chức** (support@…) → connect org-scope bằng OAuth của
  chính mailbox dùng chung đó.
- **Remove member** không tự động disconnect connection (connection thuộc org);
  admin thấy mọi connection org-wide và disconnect thủ công khi cần.
- Ràng buộc `UNIQUE (org_id, account_email)`: một mailbox chỉ connect một lần
  trong mỗi org.

## 5. Guard xóa member (tham chiếu #93)

`DELETE /api/orgs/{id}/members/{user_id}` từ chối:
1. Target có role `platform_admin` → 403
2. Tự xóa chính mình → 400
3. Target là org_admin/admin cuối cùng còn active → 400

## 6. Đã verify (2026-08-25)

Mô phỏng filter sidebar với permission set từng role (pure function, cùng logic
`hasUiPermission`):

- `user`: 15 mục hiện — ẩn MCP Servers, Providers, Evaluations, Members, Debug,
  Email Operations, Organizations
- `operator`: 18 mục hiện — ẩn Quotas, Members, Debug, Organizations
- `org_admin`: 21 mục hiện — ẩn Organizations (platformOnly)
- `platform_admin`: 22 mục — tất cả
