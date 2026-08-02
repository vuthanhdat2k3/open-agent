# M15 — Khép vòng: Trace → Eval → Cổng chặn

## Branch

`agentos-v2/m15-closed-eval-loop` từ `main` (sau khi M13 merge).

## Depends on

- **M13** — nguồn trace/audit có cấu trúc để lấy mẫu.
- **M11** — evaluation suite/case/run/result đã có.
- **M10** — agent release + rollback đã có.

Có thể làm **song song với M14** (ít đụng file chung: M14 chạm workflow
engine, M15 chạm evaluations).

## Goal

Biến mỗi sự cố production thành một test case vĩnh viễn, và chặn release
mới nếu nó làm tụt chất lượng. Đây là **điểm khác biệt thật** của OpenAgent
so với các nền tảng mã nguồn mở khác — không nền tảng nào khép trọn vòng này.

## Bối cảnh: đã có sẵn gì

- `EvaluationSuite`: `agent_id`, `dataset_version`.
- `EvaluationCase`: `input`, `expected_output`, `required_substrings`,
  `expected_tools`, `forbidden_patterns`, `max_latency_ms`, `max_cost_usd`,
  `metadata`, `ordinal`, `added_in_version`.
- `EvaluationRun`: `suite_id`, `agent_release_id`, `baseline_run_id`,
  `dataset_version`, `execution_mode`, `status`, `pass_rate`,
  `average_latency_ms`, `total_cost_usd`.
- Grader tất định (M11): exact match, substring, forbidden regex, required
  tools, max latency, max cost, pass rate.
- CLI `python -m app.evals.cli ... --min-pass-rate` với exit code cho CI.

Ba mảnh còn thiếu: **lấy mẫu trace**, **grader retrieval**, **auto-rollback**.

## Scope

**Trong phạm vi**: sampler trace→case, grader nhóm retrieval, gate publish,
auto-rollback theo ngưỡng.

**Ngoài phạm vi**: LLM-as-a-judge (phá nguyên tắc "nhân tất định" — chỉ thêm
sau, dạng grader tuỳ chọn có credential gate), canary theo %.

## Phần 1 — Sampler: trace → eval case

### Data model

- `EvaluationCase` thêm cột:
  - `source: str = "manual"` — `"manual" | "sampled"`
  - `source_run_ref: str | None` — id của session/workflow_run gốc
  - `sampled_reason: str | None` — vì sao được chọn
- `SamplingPolicy` (bảng mới): `org_id`, `agent_id`, `suite_id`, `enabled`,
  `reasons: list[str]`, `max_per_day: int`, `created_by_user_id`.

### Tiêu chí lấy mẫu (theo thứ tự ưu tiên)

Nguồn dữ liệu là `audit_logs` (M13) + `sessions`/`workflow_runs`:

1. Run có `guardrail.injection_flagged` hoặc `guardrail.secret_redacted`.
2. Run kết thúc `failed` / tool call `status=error`.
3. Run bị người dùng chấm điểm thấp (nếu đã có feedback; nếu chưa thì bỏ qua
   tiêu chí này, **không** tự bịa thêm bảng feedback trong M15).
4. Run chạm `max_iterations` mà chưa xong (dấu hiệu loop).

### Quy tắc bắt buộc

- Case sinh ra **luôn ở trạng thái chờ duyệt**, không tự động vào dataset.
  Người phải xác nhận `expected_output` — máy không biết đáp án đúng là gì.
  Đây là ranh giới quan trọng: sampler đề xuất, con người quyết định.
- Thêm case → tăng `dataset_version` (giữ đúng semantics M11).
- Input được lấy mẫu phải đi qua `scan_and_redact` trước khi lưu — dataset
  eval không được chứa secret của production.
- Tôn trọng `max_per_day` để không làm phình dataset.

## Phần 2 — Grader retrieval

Nhắm thẳng vào nguyên nhân gốc của 61% sự cố đa tầng.

`EvaluationCase` thêm cột:

- `expected_doc_ids: list[str]` — chunk/doc nào *nên* được truy xuất
- `min_recall_at_k: float | None`, `k: int | None`
- `min_groundedness: float | None`

Grader mới trong `app/evals/graders/retrieval.py`:

| Grader | Cách tính | Tất định? |
|---|---|---|
| `recall_at_k` | \|retrieved ∩ expected\| / \|expected\| trong top-k | Có |
| `mrr` | 1/rank của doc đúng đầu tiên | Có |
| `groundedness` | tỷ lệ câu trong output có n-gram overlap ≥ ngưỡng với chunk đã truy xuất | Có (heuristic, không cần LLM) |

Để chấm được, `EvaluationResult` phải lưu `retrieved_doc_ids: list[str]` —
executor cần bắt được danh sách chunk mà `rag_search` trả về. Lấy từ
`ToolCallRecord` (M14) nếu M14 đã merge, ngược lại parse từ tool result.

> Groundedness bằng n-gram là heuristic có trần rõ ràng — nó bắt được
> "bịa hoàn toàn" chứ không bắt được "diễn giải sai tinh vi".
> `# ponytail: n-gram overlap, nâng lên NLI model nếu tỷ lệ false-negative cao`

## Phần 3 — Cổng chặn & auto-rollback

- `AgentRelease` thêm: `quality_gate_status: str = "unknown"`
  (`unknown | passed | failed`), `quality_gate_run_id: str | None`.
- **Chặn publish**: `POST /api/agents/{id}/releases/{rid}/publish` trả 409
  nếu suite bắt buộc chưa chạy hoặc `pass_rate` tụt so với baseline quá
  ngưỡng. Có cờ `force: bool` cho owner (ghi audit `release.gate_overridden`).
- **Auto-rollback**: job định kỳ chạy suite nhẹ trên release đang active;
  nếu `pass_rate` tụt quá `rollback_threshold` → gọi đúng cơ chế rollback
  của M10, ghi audit `release.auto_rolled_back`.
  - Bắt buộc có **cooldown** để tránh flap qua lại giữa 2 release.
  - Bắt buộc **tắt được** (`auto_rollback_enabled`, mặc định `False` —
    tự động rollback production là hành vi mạnh, phải chủ động bật).

## Files to add

- `backend/app/evals/sampler.py`
- `backend/app/evals/graders/retrieval.py`
- `backend/app/models/sampling_policy.py`
- `backend/alembic/versions/00XX_eval_sampling_and_retrieval.py`
- `backend/tests/test_eval_sampler.py`
- `backend/tests/test_retrieval_graders.py`
- `backend/tests/test_release_quality_gate.py`
- `frontend/app/evaluations/sampled/page.tsx` — màn duyệt case được đề xuất

## Files to modify

- `backend/app/models/evaluation.py` — cột mới cho case + result
- `backend/app/models/agent_release.py` — cột quality gate
- `backend/app/api/v1/routes/evaluations.py` — route duyệt case đề xuất
- `backend/app/services/evaluation_service.py` — nghiệp vụ sampler + duyệt
- `backend/app/services/agent_service.py` — chặn publish khi gate fail
- `backend/app/evals/cli.py` — thêm `--require-retrieval-gate`
- `backend/app/worker.py` — job định kỳ auto-rollback

## Suggested commit breakdown

1. `feat(agentos-m15): sampling_policy model + eval case source columns`
2. `feat(agentos-m15): trace sampler proposes cases from audit signals`
3. `feat(agentos-m15): human approval flow for sampled cases`
4. `feat(agentos-m15): retrieval graders (recall@k, mrr, groundedness)`
5. `feat(agentos-m15): capture retrieved_doc_ids in evaluation results`
6. `feat(agentos-m15): quality gate blocks release publish`
7. `feat(agentos-m15): scheduled auto-rollback with cooldown (opt-in)`
8. `feat(agentos-m15): frontend review screen for sampled cases`
9. `test(agentos-m15): sampler + retrieval graders + gate tests`

## Tests to write

`test_eval_sampler.py`:

- Run có `guardrail.injection_flagged` → sinh 1 case đề xuất với
  `sampled_reason` đúng.
- Case đề xuất **không** vào dataset cho tới khi được duyệt (assert
  `dataset_version` chưa tăng).
- Duyệt case → `dataset_version` tăng đúng 1.
- Input chứa secret → case đã lưu **không** chứa secret (assert tường minh).
- `max_per_day` được tôn trọng.

`test_retrieval_graders.py`:

- `recall_at_k`: retrieved chứa 2/3 expected trong top-5 → 0.667.
- `mrr`: doc đúng ở vị trí 3 → 0.333.
- `groundedness`: output copy nguyên văn từ chunk → điểm cao; output bịa
  hoàn toàn → điểm thấp.
- Grader chạy được **không cần credential provider** (nguyên tắc M11).

`test_release_quality_gate.py`:

- Publish release khi gate `failed` → 409.
- `force=true` bởi owner → publish được + audit `release.gate_overridden`.
- `force=true` bởi developer → 403.
- Auto-rollback tắt mặc định; bật + pass_rate tụt → rollback + audit.
- Cooldown ngăn rollback liên tiếp.

## CI additions

- Chạy grader retrieval trên fixture tất định trong job backend.
- Mở rộng CLI gate hiện có: thêm case retrieval vào smoke dataset của CI.

## PR checklist

```
- [ ] Case lấy mẫu LUÔN cần người duyệt, không tự vào dataset (có test)
- [ ] Case lấy mẫu đã qua scan_and_redact, không chứa secret (có test assert)
- [ ] dataset_version tăng đúng semantics M11
- [ ] Grader retrieval tất định, chạy được không cần credential provider
- [ ] Groundedness có comment ponytail nêu rõ trần của heuristic
- [ ] Publish bị chặn khi gate fail; force chỉ owner được dùng và có audit
- [ ] Auto-rollback MẶC ĐỊNH TẮT, có cooldown, có audit khi kích hoạt
- [ ] Mọi bảng mới có org_id, mọi query scope theo tenant
- [ ] Không thêm LLM-as-a-judge vào đường chạy bắt buộc
- [ ] pytest xanh, CI xanh
```