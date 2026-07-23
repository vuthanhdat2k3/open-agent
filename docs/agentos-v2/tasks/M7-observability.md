# M7 — Observability

## Branch
`agentos-v2/m7-observability` từ `main`.

Có thể bắt đầu song song ngay sau M3 (đã có `org_id`/user context để gắn
nhãn), nhưng khuyến nghị merge **sau** M4-M6 để có đủ điểm gắn span/metric
đáng đo (tool call, node run, approval, sandbox). Nếu làm sớm hơn, chấp nhận
việc phải quay lại thêm span cho các phần được merge sau.

## Scope
**Trong phạm vi**: structured logging, OpenTelemetry tracing, Prometheus
metrics, audit log table + ghi log tại các điểm nhạy cảm, Grafana dashboard +
Prometheus alert rule (định nghĩa, chưa cần chạy thật trong CI).
**Ngoài phạm vi**: dựng hạ tầng thật (otel-collector/prometheus/grafana/loki
containers) — đó là phần compose của M8; M7 chỉ code phần app + config file
cho các dashboard/alert, M8 mới wiring vào docker-compose.

## Depends on
Không phụ thuộc cứng milestone nghiệp vụ nào để bắt đầu, nhưng audit log
cần `User`/`ApiKey` từ M2 để biết "ai" thực hiện hành động.

## Files to add
- `backend/app/core/observability/__init__.py`
- `backend/app/core/observability/logging.py`
- `backend/app/core/observability/tracing.py`
- `backend/app/core/observability/metrics.py`
- `backend/app/models/audit_log.py`
- `backend/alembic/versions/00XX_add_audit_log.py`
- `backend/app/core/observability/audit.py` (`log_action(org_id, actor,
  action, resource_type, resource_id, metadata)`)
- `observability/grafana/dashboards/usage-cost.json`
- `observability/grafana/dashboards/latency-errors.json`
- `observability/grafana/dashboards/queue-worker-health.json`
- `observability/prometheus/alerts.yml`
- `backend/tests/test_observability_metrics.py`
- `backend/tests/test_audit_log.py`

## Files to modify
- `backend/pyproject.toml` — thêm `structlog`,
  `opentelemetry-sdk`, `opentelemetry-instrumentation-fastapi`,
  `opentelemetry-exporter-otlp`, `prometheus-fastapi-instrumentator`.
- `backend/app/config.py` — thêm `otel_exporter_endpoint`, `otel_enabled:
  bool = False` (tắt mặc định cho dev đơn giản, bật qua env khi có
  collector), `log_format: Literal["json","console"] = "json"`.
- `backend/app/main.py` — middleware gán `request_id` (uuid4) vào
  `structlog.contextvars`; init `Instrumentator().instrument(app).expose(app)`
  cho `/metrics`; init OTel `FastAPIInstrumentor.instrument_app(app)` nếu
  `otel_enabled`.
- `backend/app/core/agent_loop.py` — bọc span quanh mỗi iteration
  (`with tracer.start_as_current_span("agent_loop.iteration", attributes=
  {...})`) và quanh mỗi tool call; tăng `Counter`/`Histogram` từ
  `metrics.py`.
- `backend/app/core/workflow/engine.py` — span quanh mỗi node run; metric
  `workflow_run_duration_seconds`.
- `backend/app/core/tools/sandbox.py` — metric `sandbox_executions_total{status}`.
- Các route nhạy cảm (`auth.py` login, `orgs.py` member/role change,
  `approvals.py` decide, `agent_loop.py` khi chạy tool `risk_tier=dangerous`)
  — gọi `audit.log_action(...)`.

## Step-by-step
1. `logging.py` trước — thuần cấu hình, không phụ thuộc phần khác, dễ test
   độc lập (assert log output là valid JSON có field `request_id`).
2. `metrics.py` — định nghĩa Counter/Histogram, `Instrumentator` mount vào
   `main.py`, kiểm `curl localhost:8000/metrics` trả đúng format Prometheus.
3. `tracing.py` — init TracerProvider, nhưng **để `otel_enabled=False` mặc
   định** để không bắt buộc có OTLP collector chạy mới dev được; test chỉ
   cần assert không crash khi disabled, và assert span được tạo (dùng
   in-memory exporter của OTel SDK cho test) khi enabled.
4. `AuditLog` model + `audit.py` helper — wiring vào các điểm liệt kê ở
   trên, mỗi điểm 1 dòng gọi, không làm phức tạp logic nghiệp vụ xung quanh.
5. Viết dashboard JSON — không cần Grafana thật để viết, nhưng nên tự dựng
   Grafana local 1 lần (`docker run grafana/grafana`) để import thử, xác
   nhận JSON valid trước khi commit.
6. Viết `alerts.yml` theo cú pháp Prometheus alerting rule chuẩn, validate
   bằng `promtool check rules alerts.yml` nếu có `promtool` sẵn (không bắt
   buộc cài trong CI ở M7, chỉ cần valid YAML).

## Suggested commit breakdown
1. `feat(agentos-m7): structlog json logging with request_id context`
2. `feat(agentos-m7): prometheus metrics + /metrics endpoint`
3. `feat(agentos-m7): opentelemetry tracing (feature-flagged, off by default)`
4. `feat(agentos-m7): audit_log model + log_action helper`
5. `refactor(agentos-m7): wire audit logging into auth/org/approval/dangerous-tool paths`
6. `feat(agentos-m7): grafana dashboards + prometheus alert rules`
7. `test(agentos-m7): metrics + audit log tests`

## Tests to write
- `test_observability_metrics.py`: gọi 1 route bất kỳ → `/metrics` chứa
  đúng counter đã tăng (`http_requests_total` từ instrumentator, và ít nhất
  1 custom counter nếu route đó đi qua tool call).
- `test_audit_log.py`: login thành công → 1 `AuditLog` row action="login";
  đổi role member → 1 row action="membership.role_changed" với
  `metadata={"from":..., "to":...}`; revoke API key → 1 row tương ứng.
- Test tracing: bật `otel_enabled=True` trong test config với in-memory
  span exporter (`opentelemetry.sdk.trace.export.InMemorySpanExporter`) →
  chạy 1 agent loop ngắn → assert có span `agent_loop.iteration` và span con
  tool call với đúng attribute `org_id`.

## CI additions
Không cần service container mới (OTel/Prometheus/Grafana không chạy trong
CI test — chỉ test code app, không test hạ tầng thật, đó là việc của M8 nếu
muốn thêm smoke test compose). Thêm bước validate YAML:
`python -c "import yaml; yaml.safe_load(open('observability/prometheus/alerts.yml'))"`
vào job `backend` hoặc 1 job `lint-observability` nhẹ riêng.

## PR checklist
```
- [ ] Log output là JSON, có request_id xuyên suốt 1 request
- [ ] /metrics trả đúng format Prometheus, có ít nhất các custom counter/histogram đã liệt kê
- [ ] OTel tracing tắt mặc định (otel_enabled=False), không bắt buộc collector để dev/test chạy được
- [ ] Bật tracing tạo đúng span cha-con agent_loop → tool call, có test bằng in-memory exporter
- [ ] AuditLog ghi đúng tại: login, đổi role, tạo/revoke api key, approval decide, chạy tool dangerous
- [ ] Grafana dashboard JSON + Prometheus alert rule tồn tại, valid syntax
- [ ] pytest xanh, CI xanh
```
