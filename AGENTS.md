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

> 2026-09-06: Đã merge PR #296 (fix multi-tenant RAG: namespace theo org + cá nhân cho vector DB, thêm quyền `files:personal:manage` để user tự ingest tài liệu qua trang `/files`) và PR #299 (fix bug phát hiện khi live-test: rag-service `/ingest/file` thiếu auto-create collection; `rag_search` fan-out dùng `asyncio.gather` vi phạm giới hạn concurrency của SQLAlchemy AsyncSession) vào `dev`, đã đồng bộ `deploy/dev`. Đã live-test bằng tài khoản operator + 2 user thật (tạo mới `user2@protonx.com`) trên ProtonX: ingest 3 tài liệu khác nội dung, xác nhận qua chat mỗi user chỉ thấy tài liệu dùng chung + tài liệu cá nhân của chính mình, không thấy được tài liệu cá nhân của user khác.

> 2026-09-06: Đã merge PR #297 vào `dev` và deploy lên `deploy/dev` qua PR #298 (Refactor Compaction theo chuẩn DeepSeek Harness: append-only không xóa tin nhắn cũ trong Message table, chèn checkpoint marker role=compaction tại đúng ranh giới phân tách; component CompactionItem collapsed-by-default với Sparkles icon màu amber, thống kê số tin nhắn và tokens đã nén, accordion disclosure xem Markdown tóm tắt; cập nhật thuật toán đo tokens /context tự động trừ dải tin nhắn bị shadow và phản ánh chính xác dung lượng model nạp).

> 2026-09-06: Đã merge PR #294 vào `dev` và deploy lên `deploy/dev` qua PR #295 (Triển khai thực tế cho /compact và /clear: endpoint POST /api/sessions/:id/compact tự động tóm tắt ngữ cảnh hội thoại, sinh event COMPACTION_SUMMARY với surface_op replace/shadowing dải tin nhắn cũ trong Session Event Log, dọn dẹp messages cũ trong DB và chèn tin nhắn tóm tắt; endpoint POST /api/sessions/:id/clear xóa sạch Message, SessionEvent và SessionMemory trong cơ sở dữ liệu; đấu nối trực tiếp frontend Slash Commands, tự động refetch messages và cập nhật context token gauge).

> 2026-09-06: Đã merge PR #292 vào `dev` và deploy lên `deploy/dev` qua PR #293 (Sửa triệt để lỗi context tokens = 0 trong modal /context: truyền messages={messages} cho ChatInput, sửa parser input_tokens/output_tokens từ database khi reload tin nhắn, tính toán Base Context cho Agent từ system_prompt và tools schema khi phiên mới tinh, bổ sung badge chỉ báo nguồn token "Lượt gần nhất" hoặc "Ước tính").

> 2026-09-05: Đã merge PR #290 vào `dev` và deploy lên `deploy/dev` qua PR #291 (Hiển thị trực quan Cửa sổ ngữ cảnh Context Window và số Tokens thực tế của session trong /context: Hero Card Gauge Bar với 3 dải màu Xanh/Vàng/Đỏ cảnh báo khi đầy; thống kê tokens đã dùng, khả dụng còn lại và giới hạn model; cảnh báo thông minh khi vượt quá 75% kèm nút kích hoạt nhanh /compact; phân tích chi tiết phiên với số lượt hỏi, tổng tin nhắn, prompt/output tokens và độ trễ lượt gần nhất).

> 2026-09-05: Đã merge PR #288 vào `dev` và deploy lên `deploy/dev` qua PR #289 (Chuẩn hóa toàn diện cơ chế Slash Commands: khắc phục lỗi di chuyển phím mũi tên bằng scrollIntoView và wrap-around; hỗ trợ phím Tab và hover chuột; menu glassmorphism với icon badge cho 10 lệnh và footer phím tắt; thay thế popup toast Sonner của /context, /usage, /help bằng modal CommandInfoDialog chuyên nghiệp 3 tab gồm chi tiết Model/Agent/Policy/Session ID với nút copy, 4 metric cards tổng hợp chi phí USD/tokens và bảng tra cứu lệnh; tự động dọn sạch draft sau khi chạy lệnh; bổ sung 15 unit tests cho registry và command handlers).

> 2026-09-05: Đã merge PR #282 vào `dev` và deploy lên `deploy/dev` qua PR #283 (Lưu trạng thái mở Canvas và tệp xem dở qua reload bằng Zustand persist openagent-canvas; nâng cấp thanh kéo giãn Resizable Divider với nút Grab Pill nổi GripVertical trực quan ở giữa màn hình).

> 2026-09-05: Commit trực tiếp lên `dev` (8351255) và merge lên `deploy/dev` (3250a34) theo yêu cầu người dùng (Sửa triệt để lỗi treo write_file/run_code do idempotency_key vượt quá VARCHAR(128) — thêm migration 0070 nới cột lên 256; thêm pool_timeout=10s cho SQLAlchemy engine; giới hạn trần timeout sandbox 300s và đảm bảo dọn dẹp container Docker khi bị cancel; bổ sung cost_usd và cờ real/estimated cho mọi generation Langfuse, trace thêm Test Connection/Model Test; sửa lỗi login nuốt mất thông báo lỗi thật).

> 2026-09-05: Commit trực tiếp lên `dev` (9d187ce) và merge lên `deploy/dev` (cfe1f1a) theo yêu cầu người dùng (Thêm Ops & Reliability Agent — agent giám sát có kiểm soát, chỉ platform_admin, quét Langfuse + system health định kỳ mỗi 15 phút, ghi finding kèm bằng chứng cụ thể và đề xuất "Suggested fix:" bằng văn bản, không có bất kỳ tool nào tự sửa code/config; migration 0071 thêm agents.visibility, sessions.workspace_override_path (chưa dùng, để dành), bảng ops_findings; RBAC platform_admin bổ sung tối thiểu agents:run/tools:use:{safe,read,network}/approvals:manage chỉ áp dụng cho agent visibility=platform_admin; execution_policy khoá cứng "manual" không cho override qua request).

> 2026-09-05: Đã merge PR #279 vào `dev` và deploy lên `deploy/dev` qua PR #280 (Toàn màn hình Canvas thoát khỏi stacking context bằng React Portal z-[100] không bị AppHeader che khuất, nút Thu nhỏ nổi bật kèm phím tắt Esc; bổ sung thanh Resizable Divider Handle kéo giãn trái/phải tùy chỉnh kích thước 25%-75%, nhấp đúp reset 50% và bảo vệ sự kiện chuột trên iframe).

> 2026-09-05: Đã merge PR #277 vào `dev` và deploy lên `deploy/dev` qua PR #278 (Khắc phục lỗi tràn mép phải và cắt cụt Canvas Panel trên desktop: nhóm ChatThread và ChatCanvasPanel vào container dùng chung flex-row min-w-0 sau ChatSidebar, chia tỉ lệ 50/50 trên lg và 52/48 trên xl vừa khít 100% màn hình, thu gọn nhãn nút trên màn hình laptop tránh che tiêu đề).

> 2026-09-05: Đã merge PR #274 vào `dev` và deploy lên `deploy/dev` qua PR #275 (Tối ưu giao diện Responsive toàn diện: ChatSidebar mobile slide-over Sheet drawer, ChatCanvasPanel mobile/tablet full overlay drawer, cuộn ngang min-w-[600px] cho tất cả Table, ẩn Companion3D trên mobile, co giãn Model Selector và grid 1 cột trên màn hình nhỏ).

> 2026-09-05: Đã merge PR #271 vào `dev` và deploy lên `deploy/dev` qua PR #273 (Khắc phục lỗi đứt đoạn session_id khi Subagent tạo artifact: truyền session_id vào run_agent_loop và ToolContext, loại bỏ nhánh elif root_run_id gây bỏ qua root_run_id khi gom file cuối lượt, chuẩn hóa prompt Coder và Orchestrator luôn xuất kèm khối mã nguồn markdown và hướng dẫn dùng Thẻ tệp / Side Canvas Panel).

> 2026-09-05: Đã merge PR #269 vào `dev` và deploy lên `deploy/dev` qua PR #270 (Khắc phục lỗi phạm vi tệp theo turn: chỉ hiển thị đúng các tệp sinh ra hoặc cập nhật trong lượt đó thay vì gom toàn bộ tệp trong session, chuẩn hóa thuật toán phân bổ tệp lịch sử chat theo timestamp).

> 2026-09-05: Đã merge PR #267 vào `dev` và deploy lên `deploy/dev` (Bổ sung Side Code & Artifacts Canvas Panel docked bên cạnh Chat hiển thị mã nguồn có line numbers, tab xem trước HTML/SVG iframe sandbox và Sandbox Terminal Console chạy mã nguồn Python/JS/Bash realtime; tích hợp nút Canvas trên CodeBlockWithAction và FileAttachmentCard).

> 2026-09-05: Đã merge PR #265 vào `dev` và deploy lên `deploy/dev` (Hiển thị trực tiếp các File Attachment Cards sinh ra bởi trợ lý AI trong tin nhắn chat, hỗ trợ thumbnail lightbox preview và tải file về máy, backfill lịch sử chat tự động từ WorkspaceArtifact).

> 2026-09-05: Đã merge PR #262 vào `dev` và deploy lên `deploy/dev` (Bổ sung hỗ trợ tệp đính kèm gồm ảnh multimodal vision và trích xuất text tài liệu trên Telegram/Discord, thêm GET /api/files/:id/content phục vụ inline render và tải file, nâng cấp giao diện Web Chat với FileAttachmentCard hỗ trợ thumbnail preview trực quan và lightbox phóng to ảnh).

> 2026-09-05: Đã merge PR #261 vào `dev` và deploy lên `deploy/dev` (Bổ sung Telegram real-time long-polling TelegramBotManager không cần webhook/domain công khai, tối ưu HTTP keep-alive connection pooling cho Telegram & Discord drivers, tách streaming progressive flusher chạy nền non-blocking giúp giảm độ trễ phản hồi từ 19.2s xuống 2s, bổ sung Markdown-to-HTML converter và tinh chỉnh auto-scroll stream).

> 2026-09-05: Đã merge PR #260 vào `dev` và deploy lên `deploy/dev` (Sửa lỗi cuộn tự do trên trang Chat khi đang stream: thay thế isProgrammaticScrollRef bằng isSmoothScrollingRef, cho phép kéo scrollbar, lăn chuột và vuốt trackpad mượt mà không bị giật về đáy).

> 2026-09-04: Đã merge PR #252 vào `dev` và deploy lên `deploy/dev` (Sửa lỗi "Organization context required" trên trang Tích hợp: giải mã application session cookie và tự động fallback về active membership trong `get_current_org_id`, đảo thứ tự dependency trong `start_ci_oauth`, tự động đồng bộ active org và đính kèm `X-Org-Id` trên mọi request frontend).

> 2026-09-03: Đã merge trực tiếp vào `dev` và dọn dẹp branch `feat/fix-chat-stream-scroll-and-flicker` (Sửa lỗi nội dung biến mất sau khi stream xong, cho phép scroll tự do khi đang sinh token và sửa lỗi 500 ResponseValidationError tier fast làm mất switch models trong chat).

> 2026-09-03: Đã merge trực tiếp vào `dev` và dọn dẹp branch `feat/fix-session-update-user-role` (Sửa triệt để lỗi user.role None khi gọi PATCH /api/sessions/:id bằng cách inject authz context PrincipalContext và gán user.role từ membership).

> 2026-09-03: Đã merge trực tiếp vào `dev` và dọn dẹp branch `feat/allow-user-role-full-access` (Cho phép role user được bật và sử dụng execution policy full-access) theo yêu cầu người dùng.

> 2026-09-03: Commit trực tiếp lên `dev` (db39a53): fix(chat): add userScrolledUp lock and disable overflowAnchor to allow free scrolling during streaming — Sửa triệt để lỗi giật về đáy và không cuộn được lên xem tin nhắn cũ khi AI đang sinh token.

> 2026-09-03: Commit trực tiếp lên `dev` (dd27066): fix(auth): ensure SSO button is displayed when local auth is disabled — Thêm nút "Tiếp tục qua SSO Doanh nghiệp" khi màn hình login hiện "Local authentication is disabled", sửa API_INTERNAL_URL để Next.js rewrite proxy đúng sang container backend.

> 2026-09-03: Commit trực tiếp lên `dev` (6cedb7e + 4b0cfd1): fix(chat): emit durable error event on uncaught provider exceptions + show full provider error message when stream ends without terminal event — Thay vì stream đóng im lặng khi quota hết hoặc lỗi provider, backend ghi event error vào durable log, frontend fetch task.result và hiển thị toast lỗi đầy đủ cho user.

> 2026-09-02: Đã merge PR #238 vào `dev` và dọn dẹp worktree `feat/operator-workflow-actions-fix` (Cho phép Operator cả Cài đặt và Chỉnh sửa trực tiếp trên Canvas các Marketplace templates, sửa backfill legacy custom templates).

> 2026-09-02: Đã merge PR #234 và #236 vào `dev`, deploy thành công lên `deploy/dev` (PR #237) và dọn dẹp worktree `feat/nondestructive-system-templates-sync` (Đồng bộ non-destructive cho providers, workflow templates, agent templates và xử lý triệt để đụng độ khóa chính multi-org).

> 2026-09-02: Đã xóa các nhánh remote đã merge vào `dev`: `origin/docs/demo-do-deploy-guide`, `origin/feat/system-agent-startup-sync`. Sửa luồng phê duyệt đa tầng sub-agent không bị treo, fix overlap nút fullscreen/close và hoàn thiện URL query parameter deep linking + backdrop close cho Web Artifact Preview Dialog.

> 2026-09-01: Đã dọn dẹp worktree và branch `docs/demo-do-deploy-guide` (Viết docs/demo-digitalocean-deploy.md: hướng dẫn deploy demo full-stack lên DigitalOcean + phân tích chi phí) sau khi đã merge vào `dev`.

> 2026-09-01: Đã dọn dẹp worktree và branch `feat/system-agent-startup-sync` (Đồng bộ System Agent Blueprints lúc startup) sau khi đã merge vào `dev`.

> 2026-09-01: Đã merge trực tiếp vào `dev` và dọn dẹp worktree `feat/sandbox-isolation-and-operator-view` (Sandbox Isolation Zero-Trust & Live Run Output Panel Drawer, streaming real-time output, stop controls, creator deletion rights, Node.js/Python/Bash runner) theo yêu cầu người dùng.

> 2026-09-01: Đã merge trực tiếp vào `dev` và dọn dẹp worktree `feat/workflow-marketplace-scoping` (Chuẩn hóa Marketplace workflow templates: User mới có danh sách workflow trống, System Templates thuộc Marketplace toàn cục không có người tạo và không thể xóa, Custom Templates theo Org hiển thị nút Xóa/Gỡ bỏ cho chính Creator hoặc Org Admin) theo yêu cầu người dùng.

> 2026-09-01: Đã merge trực tiếp vào `dev` và dọn dẹp worktree/branch `fix/chat-session-sync-race` (Sửa triệt để race condition: dùng transitioningSessionRef/transitioningAgentRef ngăn URL watcher phục hồi session cũ trong render tick trung gian của Next.js router, tạo session mới chuẩn xác chỉ với 1 click) theo yêu cầu người dùng.

> 2026-09-01: Đã merge trực tiếp vào `dev` và dọn dẹp worktree/branch `fix/new-session-click` (Sửa lỗi URL synchronization trong useEffect: reset session khi URL chuyển về clean /chat thay vì phục hồi session từ store, giúp 1-click tạo session mới ngay lập tức) theo yêu cầu người dùng.

> 2026-09-01: Đã merge trực tiếp vào `dev` và dọn dẹp worktree/branch `fix/subagent-delegation-timeout` (Nâng ngân sách timeout_s cho call_agent và delegate_to_* lên 300s ngăn sub-agent deep reasoning timeout) theo yêu cầu người dùng.

> 2026-09-01: Đã merge trực tiếp vào `dev` và dọn dẹp worktree/branch `fix/session-delete-events` (Sửa lỗi xóa session: bổ sung xóa cascade bảng session_events, trả về JSON chuẩn và cập nhật nút xóa/đóng session trên giao diện) theo yêu cầu người dùng.

> 2026-09-01: Đã merge trực tiếp vào `dev` và dọn dẹp worktree/branch `feat/system-execution-policy` (Tinh gọn quyền thực thi Agent, chuyển giao quyền sang System/Session Policy Context chuẩn DSH) theo yêu cầu người dùng.

> 2026-09-01: Đã merge trực tiếp vào `dev` và dọn dẹp worktree/branch `feat/companion-size-config` (Cho phép operator tùy chỉnh kích thước companion 3D avatar qua preset và thanh trượt) theo yêu cầu người dùng.

> 2026-08-31: Đã merge trực tiếp vào `dev` và dọn dẹp worktree/branch `feat/org-model-tier-matrix` (Triển khai Org-wide Model Tier Matrix 3 tầng: Economy, Balanced, Frontier cho toàn bộ multi-agent network) theo yêu cầu người dùng.

> 2026-08-31: Đã merge trực tiếp vào `dev` và dọn dẹp worktree/branch `fix/static-logo-render` (render logo sidebar tĩnh unoptimized + chặn và phân tách ranh giới công cụ Orchestrator vs Worker) và `feat/agent-orchestrator-redesign` (PR #231) theo yêu cầu người dùng.

> 2026-08-31: Đã dọn dẹp worktree/branch `fix/langfuse-trace-coverage` (Sửa 3 lỗ hổng trace continuity
> của Langfuse: triager node và sub_workflow node giờ kế thừa trace_id của workflow run cha thay vì tạo
> trace mới độc lập; CI email classifier (`agent_classifier.py`) giờ được gắn `observability=` khi gọi
> `build_driver`) sau khi merge trực tiếp vào `dev` (merge commit 541c886) theo yêu cầu người dùng.

> 2026-08-30: Đã dọn dẹp toàn bộ worktree và các nhánh đã merge vào `dev` trên cả Local và Remote:
> - `feat/deploy-readiness` (PR #229, merge commit 036f5b4)
> - `feat/agent-orchestrator-redesign`, `fix/chat-500` (đã merge, chỉ có local branch, không có remote) — ghi chú lịch sử; worktree `feat/agent-orchestrator-redesign` hiện tại là phiên làm việc mới và vẫn đang hoạt động.
> - `feat/i18n-hardcode-sweep-3`, `feat/i18n-enen-tx-sweep`, `feat/workflow-audit-fixes`,
>   `audit/profile-roles-visibility` (đã merge, remote branch tồn tại nhưng không còn worktree local
>   tương ứng — đã xóa remote)

> 2026-08-27: Đã dọn dẹp toàn bộ worktree và các nhánh đã merge vào `dev` trên cả Local và Remote:
> - `feat/workflow-node-config-fix` (PR #167, Deploy PR #168)
> - `feat/workflow-canvas-console-execution` & `feat/workflow-markdown-modal-output` (PR #161, #164)
> - `fix/ruff-zitadel-service-format`
> - `feat/i18n-vi-terminology-polish` (PR #163)
> - `feat/ui-final-i18n-hardcode-cleanup` (PR #160)
> - `fix/workflow-agent-runtime-object` (PR #158)
> - `feat/auth-callback-error-redirect-ux`, `feat/automation-dag-nodes-and-template-graphs`, `feat/deep-i18n-sweep-2`, `feat/enterprise-page-taxonomy`, `feat/executive-operator-ui`, `feat/frontend-i18n-hardtext-cleanup`, `feat/member-removal-session-revocation-lifecycle`, `feat/ui-full-i18n-localization`, `feat/ui-i18n-vietnamese-english`, `feat/ui-pagination-and-deep-i18n`, `feat/zitadel-provisioning-host-pat-fix`.

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

## 10. Quy tắc bắt buộc: Chạy Full Test & Lint Local trước khi Push (Thay thế CI)

> **LƯU Ý QUAN TRỌNG:** Repo này **đã tắt CI tự động trên GitHub Actions** để tối ưu tốc độ và không làm nghẽn runner. Hệ thống **CHỈ chạy CD deployment** khi merge vào nhánh `deploy/dev`.
> 
> Vì không còn CI server kiểm tra tự động, **mọi AI Agent bắt buộc phải tự chạy kiểm tra full test, typecheck, lint ở môi trường local trước khi commit và push lên git**. Tuyệt đối không push code chưa qua kiểm thử local.

### Danh mục lệnh kiểm tra bắt buộc:

#### 1. Đối với Frontend (`frontend/`):
```bash
cd frontend
npm run lint         # Kiểm tra ESLint
npm run typecheck    # Kiểm tra TypeScript type safety
npm run test         # Chạy unit tests (Vitest)
npm run build        # Đảm bảo Next.js build bundle thành công không lỗi
```

#### 2. Đối với Backend (`backend/`):
```bash
cd backend
ruff check .         # Kiểm tra linter Python
pytest -q            # Chạy toàn bộ unit tests / integration tests
```

#### 3. Quy trình trước khi mở PR / Push:
1. Chạy pass 100% các lệnh kiểm tra trên cho phần code có thay đổi (FE / BE hoặc cả hai).
2. Nếu có lỗi lint, type error hoặc test fail, phải sửa triệt để trước khi stage và commit.
3. Push branch và tạo PR vào `dev`.
4. Khi merge PR vào `deploy/dev`, hệ thống sẽ tự động kích hoạt CD deploy stack.


