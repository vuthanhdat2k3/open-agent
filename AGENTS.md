# AGENTS.md — Quy tắc Git cho AI agent làm việc song song trên repo này

> File này dành cho AI coding agent (Kiro, Claude Code, Codex, v.v.) đọc **trước khi** sửa code hoặc chạy lệnh git. Nếu bạn là agent đang bắt đầu một task mới trong repo này, đọc toàn bộ file này trước khi thao tác.

## 1. Vì sao file này tồn tại

Repo này có thể có **nhiều agent làm việc đồng thời** trên các feature khác nhau. Nếu hai agent cùng sửa trực tiếp trên `G:\open-agent` (thư mục làm việc chính), rủi ro cụ thể:

- Agent A đang có thay đổi chưa commit; Agent B chạy `git checkout`, `git stash`, `git reset` hoặc tạo branch mới — làm mất hoặc trộn lẫn thay đổi của Agent A.
- Hai agent cùng sửa cùng file → conflict không kiểm soát được, khó rollback.
- Agent B đọc sai "trạng thái hiện tại" của code vì Agent A đang giữa một chuỗi sửa đổi chưa hoàn chỉnh.

**Giải pháp: mỗi task/feature riêng biệt chạy trong một `git worktree` riêng, trên một branch riêng.** Thư mục làm việc chính (`G:\open-agent`, branch `dev`) chỉ dùng để tích hợp sau khi từng feature branch đã hoàn thành và được review.

## 2. Quy tắc bắt buộc trước khi bắt đầu bất kỳ task nào

1. **Kiểm tra trạng thái trước khi làm gì cả:**
   ```bash
   git worktree list
   git status --short --branch
   git branch -a
   ```
   Nếu `git status` cho thấy có thay đổi uncommitted **không phải do bạn tạo ra trong task hiện tại**, đó là dấu hiệu một agent/người khác đang làm việc trong đúng thư mục này. **Không** chạy `git checkout`, `git reset --hard`, `git stash`, hoặc `git clean` để "dọn sạch" — những thay đổi đó không thuộc về bạn.

2. **Không làm việc trực tiếp trên `dev` hoặc `main`.** Luôn tạo worktree + branch riêng cho task của mình (xem mục 3).

3. **Không sửa file đang được agent khác sửa.** Nếu `git status` trong thư mục chính cho thấy file X đang có thay đổi uncommitted và file X không thuộc phạm vi task của bạn, tuyệt đối không đụng vào file đó dù ở worktree riêng — khi merge sẽ tạo conflict không cần thiết. Nếu buộc phải sửa cùng file, dừng lại và báo cho người dùng biết trước khi tiếp tục.

4. **Mỗi feature/task lớn = một worktree + một branch riêng**, đặt tên theo pattern:
   ```text
   branch: feat/<mô-tả-ngắn-gọn-kebab-case>
   worktree path: G:\open-agent-worktrees\<tên-branch-không-có-feat->
   ```
   Ví dụ đã có trong repo: `feat/llm-observability-langfuse`, `feat/local-postgres-migration`, `feat/provider-templates-native-drivers`, `feat/workspace-run-file`.

## 3. Cách tạo worktree cho task mới

```bash
# Từ thư mục chính G:\open-agent, đảm bảo dev đã cập nhật:
git fetch origin
git checkout dev
git pull origin dev

# Tạo worktree mới cho task, branch mới rẽ từ dev:
git worktree add ../open-agent-worktrees/<ten-task> -b feat/<ten-task> dev
```

Sau đó **chuyển toàn bộ việc code sang thư mục worktree mới** (`G:\open-agent-worktrees\<ten-task>`), không code tiếp trong `G:\open-agent`.

Kiểm tra sau khi tạo:

```bash
git worktree list
```

Phải thấy worktree mới xuất hiện, trỏ đúng branch `feat/<ten-task>`.

## 4. Trong lúc làm việc trong worktree

- Commit thường xuyên trên branch riêng của mình (`feat/<ten-task>`), không cần chờ xong toàn bộ task mới commit.
- Không `git push --force`, không `git rebase` lên branch của agent khác.
- Không chạy lệnh git tại `G:\open-agent` (thư mục chính) khi đang trong task ở worktree — trừ `git fetch`/`git pull` để đồng bộ `dev` khi cần rẽ branch mới.
- Trước khi mở PR / báo hoàn thành: `git fetch origin && git log dev..HEAD --oneline` để xem branch của mình đang lệch `dev` bao nhiêu, để biết có cần rebase/merge `dev` mới vào trước không.

## 5. Khi hoàn thành task

1. Đảm bảo test pass trong worktree của mình (`pytest -q` ở `backend/`, `npm run typecheck && npm run build` ở `frontend/` — theo đúng phần "Testing" trong `README.md`).
2. Push branch: `git push -u origin feat/<ten-task>`.
3. Tạo PR vào `dev` (không vào `main` trừ khi được yêu cầu rõ):
   ```bash
   gh pr create --base dev --head feat/<ten-task> --title "..." --body "..."
   ```
4. **Không tự merge PR của mình** trừ khi người dùng yêu cầu rõ ràng.
5. Sau khi PR được merge, dọn worktree:
   ```bash
   git worktree remove ../open-agent-worktrees/<ten-task>
   git branch -d feat/<ten-task>   # chỉ sau khi đã merge
   ```

## 6. Việc KHÔNG bao giờ tự làm nếu chưa hỏi người dùng

Theo đúng mức độ rủi ro — các lệnh sau **luôn cần xác nhận rõ từ người dùng** trước khi chạy, bất kể đang ở worktree nào:

- `git push --force` / `git push -f`
- `git reset --hard`
- `git clean -f` / `git clean -fd`
- `git branch -D` (xóa branch chưa merge)
- `git worktree remove --force` (khi worktree còn thay đổi chưa commit)
- Bất kỳ lệnh nào sửa/xóa file trong worktree hoặc branch của một agent khác.

## 7. Ghi chú theo dõi worktree đang tồn tại (agent cập nhật khi tạo/xóa worktree)

> Agent tạo worktree mới: thêm một dòng vào bảng dưới. Agent xóa worktree: xóa dòng tương ứng. Giữ bảng này khớp với `git worktree list` thực tế.

| Branch | Worktree path | Phạm vi/task | Agent/người phụ trách |
|---|---|---|---|
| `dev` | `G:\open-agent` | Nhánh tích hợp chính — không code trực tiếp ở đây | — |

> 2026-08-27: Đã dọn dẹp worktree/branch `feat/workflow-canvas-console-execution` và `feat/workflow-markdown-modal-output` (Nâng cấp Workflow: Markdown Report Modal, Node Inspector Markdown, Persist Agent Output & KPI, Dynamic Input, Resizable Console, Auto Layout, Tool sanitization) sau khi merge PR #161 & #164 vào `dev`.

> 2026-08-26: Đã dọn dẹp worktree/branch `feat/ui-pagination-and-deep-i18n` (Đồng bộ phân trang thông minh ẩn khi <= 1 trang, sửa layout automations/workspace/debug/email-intelligence, bản địa hóa sâu 100%) sau khi merge vào `dev` và deploy thành công lên `deploy/dev`.

> 2026-08-26: Đã dọn dẹp worktree/branch `feat/ui-full-i18n-localization` (Bản địa hóa 100% giao diện vi/en toàn diện cho tất cả các trang, dialogs, forms và tables) sau khi merge vào `dev` và deploy thành công lên `deploy/dev`.
> 2026-08-26: Đã dọn dẹp worktree/branch `feat/ui-i18n-vietnamese-english` (Quét toàn bộ UI, sửa lỗi chính tả ký tự và triển khai đa ngôn ngữ vi/en toàn diện) sau khi merge vào `dev` và deploy thành công lên `deploy/dev`.
> 2026-08-26: Đã dọn dẹp worktree/branch `feat/automation-dag-nodes-and-template-graphs` (Standardize Enterprise Page Taxonomy, Tab Labels, DataPagination) sau khi merge vào `dev` và deploy thành công lên `deploy/dev`.

> 2026-08-25: Đã dọn dẹp worktree/branch của các PR đã merge vào `dev`
> (#86 chat-projection-stream-target, #88 chat-tool-chips, #90 chat-markdown-links,
> #93 member-removal-guards, #95 rbac-matrix, #96 rbac-permission-audit,
> #99 chat-url-session P1+P2, #100 chat-url-sync-deadlock, #102 agent-thinking-control,
> #104 chat-streaming-debug-fix, #106 chat-streaming-text-fidelity,
> #108 chat-scroll-flicker-tool-loading-fix, #110 agent-home-redesign,
> #111 tool-live-progress-subagent-stream, #114 tool-call-debug-visibility,
> #118 rbac-matrix-ui-streamline, #120 rbac-clean-personas-knowledge-base,
> #123 platform-admin-org-member-management, #124 zitadel-auto-provision-roles).
> cùng các dòng stale của worktree không còn tồn tại. Branch
> `docs/enterprise-rbac-zitadel-design` được GIỮ (còn 3 commit chưa merge của Codex).
> 2026-08-23: Đã dọn dẹp toàn bộ worktree/branch có PR đã merge vào `dev`
> (#70–#80: enterprise-rbac-authz, enterprise-authz-hardening, enterprise-rag-ingestion,
> chat-ui-projection, alembic-revision-length, models-filter, model-test-chat,
> rag-runtime-git, workspace-run-file) cùng các dòng stale của worktree không còn tồn tại.

## 8. Quy tắc chung khác (áp dụng mọi branch/worktree)

- Không commit file `.env`, credential, database dump, backup chứa dữ liệu thật.
- Stage file cụ thể (`git add <file>`), không dùng `git add .` khi không chắc phạm vi thay đổi.
- Message commit ngắn gọn, mô tả đúng thay đổi, theo convention hiện có trong `git log` (`feat:`, `fix:`, `docs:`...).
- **Không thêm co-author trailer (ví dụ `Co-authored-by: ...`) vào commit message.** Mọi commit do agent tạo chỉ ghi tác giả thực của commit (git config), không gắn tên agent làm đồng tác giả.
- **Khi merge PR: dùng "Create a merge commit", KHÔNG dùng "Squash and merge".** Squash phá lịch sử
  atomic mà các file task yêu cầu, làm branch feature không xóa được bằng `git branch -d` sau merge,
  và gây phân kỳ `deploy/dev` so với `dev` (phải merge commit hòa giải mỗi lần sync).
- Không amend commit không phải của mình.
- Nếu phát hiện file `.kiro/` hoặc file debug tạm (`_debug_*.py`) không thuộc phạm vi task của mình xuất hiện trong `git status`, không xóa hay commit chúng — để lại cho agent/người tạo ra chúng xử lý.

## 9. Quy tắc bắt buộc về Đa ngôn ngữ (i18n vi/en) khi sửa hoặc thêm mới UI

Hệ thống giao diện của OpenAgent hỗ trợ đa ngôn ngữ đầy đủ (`vi` - Tiếng Việt và `en` - Tiếng Anh). Mọi agent khi tạo mới hoặc sửa đổi code Frontend **bắt buộc tuân thủ**:

1. **Tuyệt đối không hardcode chuỗi hiển thị** (User-facing text) chỉ bằng một ngôn ngữ hoặc chuỗi cứng trong JSX/TSX.
2. **Sử dụng Hook đa ngôn ngữ**:
   ```tsx
   import { useTranslation } from "@/lib/i18n";

   export function MyComponent() {
     const { t, dict, locale } = useTranslation();
     // Sử dụng qua dictionary có type-checking:
     // {dict.pages.agents.title}
     // Hoặc qua helper:
     // {t("pages.agents.title", "Agents")}
     // Hoặc điều kiện locale đối với câu ngắn:
     // {locale === "vi" ? "Lưu thay đổi" : "Save changes"}
   }
   ```
3. **Cập nhật đầy đủ cả 2 từ điển**: Khi thêm tính năng, trang hoặc trường mới, phải bổ sung đồng thời vào:
   - `frontend/lib/i18n/locales/vi.ts` (Từ điển Tiếng Việt)
   - `frontend/lib/i18n/locales/en.ts` (Từ điển Tiếng Anh)
   - `frontend/lib/i18n/types.ts` (Type definition tương ứng)
4. **Kiểm tra trước khi hoàn thành**: Luôn chạy `npm run typecheck && npm run build` trong `frontend/` để bảo đảm không thiếu translation key và toàn bộ các trang biên dịch thành công.

