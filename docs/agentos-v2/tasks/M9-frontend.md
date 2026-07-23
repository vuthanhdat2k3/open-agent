# M9 — Frontend

## Branch
Không phải 1 nhánh — mỗi phần bám theo backend milestone tương ứng, làm và
merge song song với milestone backend đó (giữ đúng dependency, không merge
frontend cho M9.3 trước khi M4 backend đã merge):

| Nhánh | Theo backend |
|---|---|
| `agentos-v2/m9-01-auth-ui` | M2 |
| `agentos-v2/m9-02-org-rbac-ui` | M3 |
| `agentos-v2/m9-03-approval-inbox` | M4 |
| `agentos-v2/m9-04-debug-task-tree` | M5 + M6 |
| `agentos-v2/m9-05-observability-links` | M7 |
| `agentos-v2/m9-06-tech-debt-cleanup` | không phụ thuộc, làm bất kỳ lúc nào |

## Scope
**Trong phạm vi**: UI cho toàn bộ tính năng backend mới (auth, org/member,
approval inbox, debug nâng cấp, tool risk badge) + dọn nợ kỹ thuật frontend
đã phát hiện ở lần review trước.
**Ngoài phạm vi**: không đổi UI pattern hiện có (không thêm React Flow cho
workflow editor, không viết lại chat streaming) — chỉ mở rộng thêm tính năng
mới trên nền pattern đã có (fetch thủ công + TanStack Query + Zustand nhỏ).

## Depends on
Xem bảng nhánh ở trên — mỗi phần phụ thuộc đúng 1 backend milestone.

---

### M9.1 — Auth UI (theo M2)

**Files to add**: `frontend/app/login/page.tsx`,
`frontend/app/register/page.tsx`,
`frontend/app/oauth/callback/[provider]/page.tsx`,
`frontend/lib/auth.ts` (lưu access token in-memory qua module-level
variable/React context — **không** localStorage, tránh XSS đọc token).

**Files to modify**: `frontend/lib/api.ts` (đính kèm `Authorization: Bearer`
từ `auth.ts` vào mọi request; xử lý 401 → thử `/auth/refresh` 1 lần rồi
redirect `/login` nếu vẫn fail), `frontend/app/layout.tsx` (route guard: nếu
chưa có access token và route không phải `/login|/register|/oauth/*` →
redirect).

**Test/CI**: không có test tự động cho flow OAuth thật (cần provider thật);
viết test thủ công checklist trong PR. Nếu có Playwright/Vitest sẵn trong
`package.json` (hiện tại **không có** — cần thêm nếu muốn test tự động, out
of scope milestone này trừ khi bạn muốn mở rộng).

**Commit breakdown**:
1. `feat(agentos-m9): login/register pages + auth token handling`
2. `feat(agentos-m9): oauth callback page + api client auto-refresh on 401`
3. `feat(agentos-m9): route guard redirecting unauthenticated users to /login`

---

### M9.2 — Org & RBAC UI (theo M3)

**Files to add**: `frontend/app/settings/members/page.tsx`,
`frontend/app/settings/api-keys/page.tsx`,
`frontend/components/settings/member-invite-form.tsx`,
`frontend/components/settings/api-key-create-dialog.tsx` (hiện full key 1
lần, có nút copy, cảnh báo "sẽ không hiện lại").

**Files to modify**: `frontend/hooks/index.ts` (thêm `useMembers,
useInviteMember, useUpdateMemberRole, useRemoveMember, useApiKeys,
useCreateApiKey, useRevokeApiKey`), `frontend/types/index.ts` +
`frontend/lib/schemas.ts` (thêm `Membership`, `ApiKey` type/schema).

**Commit breakdown**:
1. `feat(agentos-m9): member management page (list/invite/change role/remove)`
2. `feat(agentos-m9): api key management page (create once-shown, list, revoke)`

---

### M9.3 — Approval inbox (theo M4)

**Files to add**: `frontend/app/approvals/page.tsx`,
`frontend/components/approvals/approval-card.tsx`.

**Files to modify**: `frontend/hooks/index.ts` (`useApprovals,
useDecideApproval`), `frontend/app/layout.tsx` (badge số lượng pending trên
nav, poll nhẹ qua `useApprovals` với `refetchInterval`), `frontend/app/chat/page.tsx`
+ workflow run page (xử lý SSE event `approval_required` mới — hiện banner
"đang chờ duyệt" trong luồng chat/workflow, không chỉ ở trang `/approvals`).

**Commit breakdown**:
1. `feat(agentos-m9): approval inbox page (list, approve/reject with reason)`
2. `feat(agentos-m9): pending-approval badge in nav + polling`
3. `feat(agentos-m9): handle approval_required SSE event in chat/workflow run UI`

---

### M9.4 — Debug nâng cấp (theo M5 + M6)

**Files to modify**: `frontend/app/debug/page.tsx` — thêm tab/section "Task
tree" (fetch `GET /debug/tasks/{root_run_id}`, render dạng cây thu gọn được,
mỗi node hiện agent name, status, cost, thời gian) và "Workflow runs" (fetch
`GET /workflows/runs/{id}`, hiện bảng `WorkflowNodeRun` với status/attempt/
thời gian mỗi node, màu theo status).

**Commit breakdown**:
1. `feat(agentos-m9): task delegation tree view in debug page`
2. `feat(agentos-m9): workflow node run history view in debug page`

---

### M9.5 — Observability links (theo M7)

**Files to modify**: `frontend/app/page.tsx` (dashboard) — thêm link/embed
tới Grafana dashboard (nếu `NEXT_PUBLIC_GRAFANA_URL` được set qua env, hiện
nút "Open Grafana"; nếu không set, ẩn — không hard-code URL).

**Commit breakdown**:
1. `feat(agentos-m9): optional grafana dashboard link on main dashboard`

---

### M9.6 — Dọn nợ kỹ thuật frontend (độc lập, không phụ thuộc milestone nào)

Từ review trước đó (không phải yêu cầu mới, tiện làm cùng đợt nâng cấp lớn
này):

**Files to modify**:
- `frontend/stores/index.ts` — đổi `WorkflowState.nodes: any[]`/`edges:
  any[]` sang dùng lại `GraphNode`/`GraphEdge` từ `types/index.ts`; xoá
  `useAgentStore.selectedAgentId` nếu xác nhận thật sự không dùng ở đâu (grep
  lại trước khi xoá).
- `frontend/hooks/index.ts` — gõ kiểu `mutationFn` bằng type suy ra từ Zod
  schema (`z.infer<typeof providerCreate>` v.v.) thay vì `any`, cho toàn bộ
  mutation hiện có.

**Commit breakdown**:
1. `refactor(agentos-m9): type WorkflowState nodes/edges instead of any[]`
2. `refactor(agentos-m9): type mutation inputs from zod-inferred types instead of any`

---

## Tests to write (toàn bộ M9)
Hiện `frontend/` không có test tự động nào (`package.json` không có
`vitest`/`jest`). Milestone này **không bắt buộc** thêm testing framework
mới (out of scope, có thể là 1 milestone riêng sau nếu muốn) — thay vào đó,
mỗi PR con bắt buộc có **manual test checklist** trong PR description (xem
"PR checklist" từng phần), và `npx tsc --noEmit` + `npm run build` phải xanh
(đã có trong CI từ M0).

## CI additions
Không cần job mới ngoài CI đã có từ M0 (`frontend` job: lint + tsc + build).
Nếu M9.1-M9.5 thêm nhiều page mới, đảm bảo `npm run build` không tăng thời
gian bất thường (kiểm tra output CI, không cần threshold cứng).

## PR checklist (dùng chung mẫu này cho mỗi PR con M9.x, điều chỉnh mục theo scope)
```
- [ ] Trang/feature mới hoạt động đúng qua test thủ công (mô tả các bước đã thử)
- [ ] npx tsc --noEmit sạch, npm run build xanh
- [ ] Không dùng localStorage cho access token (chỉ in-memory + refresh cookie httponly)
- [ ] API key/secret không log ra console hay hiện lại sau lần tạo đầu
- [ ] Không phá vỡ route/feature hiện có (test nhanh qua các trang cũ: /agents, /chat, /workflows)
- [ ] CI xanh
```
