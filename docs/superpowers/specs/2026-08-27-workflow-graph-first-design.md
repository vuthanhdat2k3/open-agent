# Graph-first workflow execution — hướng C

## Mục tiêu

Biến `Workflow.graph` thành nguồn sự thật duy nhất cho việc định nghĩa và thực thi workflow. Workflow chỉ tự động chạy khi graph có trigger node phù hợp; không chọn executor riêng bằng `template_key`.

Hệ thống phải hỗ trợ user tạo workflow thủ công hoặc từ catalog, chỉnh sửa node/edge tự do, chạy thủ công, chạy theo lịch, chạy theo event/webhook, kết hợp nhiều trigger, dùng integration thật theo tenant/user, và giữ đúng logic của run đang chạy khi graph bị chỉnh sửa.

## Nguyên tắc

1. `Workflow.graph.nodes` và `Workflow.graph.edges` là cấu hình duy nhất của workflow.
2. `WorkflowTemplate` chỉ cung cấp graph khởi tạo; không quyết định runtime của workflow đã tạo.
3. Scheduler state lưu riêng chỉ là projection có thể rebuild từ graph, không phải nguồn cấu hình.
4. Mỗi run gắn với `trigger_node_id`, `trigger_type` và snapshot graph.
5. Graph không có trigger có thể lưu để chỉnh sửa nhưng không được tự động chạy; graph rỗng/không hợp lệ không được chạy.

## Graph và trigger

- `input`: entrypoint cho Run Workflow/API.
- `scheduler`: entrypoint định kỳ; config có frequency/cron/timezone.
- `integration`: entrypoint event khi integration hỗ trợ webhook/event.

Mỗi trigger node tạo một run độc lập. Với nhiều trigger, engine chỉ duyệt các node downstream của trigger đó; nhánh không reachable không chạy. `agent`, `tool`, `approval`, `triager`, `merge`, `output` chỉ chạy khi reachable từ trigger.

Scheduler node hỗ trợ hourly, daily, weekly, custom cron và IANA timezone. Một workflow có thể có nhiều scheduler node hoặc không có scheduler node.

## Scheduler projection

Graph là nguồn sự thật, nhưng worker không parse graph không giới hạn ở mỗi tick. Dùng projection rebuildable `workflow_trigger_state` gồm:

- `workflow_id`, `node_id`, `org_id`, `trigger_type`;
- `schedule_hash`, `enabled`, `next_run_at`, `last_run_at`;
- version/timestamps để optimistic concurrency.

Projection được đồng bộ atomic khi graph create/update. Reconciliation job định kỳ rebuild projection từ graph.

Worker sẽ claim trigger đến hạn bằng lease, xác nhận node còn tồn tại/enabled và hash khớp, tạo `WorkflowRun` với `trigger_node_id`, ghi dedupe key theo `(workflow_id, node_id, scheduled_for)`, rồi tính lần chạy kế tiếp. Xóa/disable/đổi lịch scheduler sẽ disable projection cũ và tạo projection mới; run đã tạo không đổi.

Projection chỉ là index/runtime state. Có thể xóa và dựng lại hoàn toàn từ `Workflow.graph`.

## Run snapshot và engine

Khi tạo run, lưu `workflow_id`, `trigger_node_id`, `trigger_type`, immutable `graph_snapshot`, graph version/hash, input, timezone và actor. Engine chạy snapshot, không đọc graph mutable trong database.

Run chờ approval, retry hoặc resume vẫn dùng snapshot cũ. Replay mặc định dùng snapshot run gốc; nếu chạy chủ động trên graph hiện tại thì phải báo rõ divergence.

## Manual, event và scheduled flows

Các graph hợp lệ cần hỗ trợ:

```text
input → agent → output
scheduler → agent → output
integration(webhook/event) → triager → agent → output
scheduler ─┐
           ├→ agent → approval → output
integration┘
```

Không có scheduler node thì không tạo lịch. Không có input node thì không chạy manual bằng input text. Event integration phải mang đúng workflow/node/org context và vượt qua kiểm tra token/connection.

## Integration, agent và quyền

Integration node lưu source, operation, connection reference và input mapping; không lưu credential. Khi lưu/chạy, connection phải tồn tại, thuộc đúng `org_id` và user được phép dùng. Connection disconnected/deleted làm node fail với mã lỗi rõ ràng. Node options lấy integration/connection thật từ API.

Agent/tool/sub-workflow phải tham chiếu object thật và được kiểm tra theo tenant. User thao tác workflow của mình theo RBAC; admin/operator thao tác trong phạm vi organization. Tất cả endpoint lọc `org_id` trước khi truy cập workflow hoặc connection.

## Catalog và migration 7 workflow

Catalog chỉ là thư viện graph mẫu. “Create from template” deep-copy graph vào workflow mới; sau đó workflow độc lập và không gọi template executor.

Data migration materialize 7 workflow cũ từ `TEMPLATE_DAGS` phải:

- chỉ cập nhật row có graph rỗng và mapping xác định;
- giữ workflow id, owner, installation, lịch sử run và tên;
- tạo scheduler projection từ scheduler node;
- không ghi đè graph đã chỉnh;
- báo số row migrated/skipped và fail rõ khi mapping mơ hồ.

Sau migration, loại bỏ `execute_catalog_report` khỏi runtime worker. Không xóa template/installation ngay; catalog và dữ liệu lịch sử vẫn tương thích.

## Validation

Create/update validate node id duy nhất, edge tồn tại, cycle theo khả năng engine, node kind/config đúng definition, trigger hợp lệ, scheduler có schedule/timezone hợp lệ, integration có source/operation/connection, agent/tool/sub-workflow đủ reference, và output/approval reachable. Graph rỗng có thể lưu nhưng không chạy. Lỗi trả theo node/field để UI focus đúng vị trí.

## Frontend

`/workflows` là bề mặt duy nhất để tạo thủ công, tạo từ catalog, thêm/xóa/nối node, cấu hình scheduler/integration/agent/tool/approval, lưu graph, pause/enable từng scheduler node, chạy manual và xem run/node logs.

UI phải hiển thị trigger đang hoạt động, lịch, connection thiếu và cảnh báo graph chưa có trigger. Catalog card chỉ gọi create editable workflow, không gọi executor.

## Error handling và concurrency

- Dedupe/lease ngăn duplicate scheduled run.
- Graph update và projection update atomic.
- Scheduler lỗi một node không làm dừng workflow khác; ghi audit lỗi theo workflow/node.
- Integration error là node error, retry theo policy node, không retry vô hạn toàn workflow.
- Approval resume dùng snapshot/checkpoint.

## Kiểm thử

Backend cần test migration 7 workflow, graph validation, zero/one/multiple scheduler, đổi/xóa/disable scheduler, reconciliation, manual/scheduled/event/mixed trigger, downstream traversal từ `trigger_node_id`, snapshot khi chờ approval, dedupe/lease, tenant isolation, connection ownership, catalog independence và không còn catalog executor runtime.

Frontend cần test tạo thủ công, scheduler config, integration connection, catalog copy rồi chỉnh graph, nhiều trigger, graph thiếu trigger/rỗng, và đầy đủ i18n vi/en.

## Trình tự triển khai

1. Schema/migration cho graph snapshot, trigger identity và projection.
2. Engine chạy từ trigger node trên snapshot.
3. Scheduler/reconciliation đọc scheduler node.
4. Worker chỉ generic graph execution; bỏ catalog executor runtime.
5. Materialize 7 workflow cũ với safety checks.
6. API/UI cho scheduler, integration và trigger status.
7. Chạy backend tests, frontend typecheck/build/test trên database đã backup.

## Ngoài phạm vi

- Không thêm node kind nếu definition hiện có đáp ứng.
- Không xóa catalog template; chỉ bỏ runtime coupling.
- Không tự động ghi đè graph đã bị user chỉnh.
- Không thay đổi credential hoặc dữ liệu ngoài workflow.
