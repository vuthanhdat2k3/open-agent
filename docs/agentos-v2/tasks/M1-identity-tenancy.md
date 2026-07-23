# M1 — Identity & Multi-tenancy (Organization / User / Membership)

## Branch
`agentos-v2/m1-identity-tenancy` từ `main` (sau khi M0 đã merge).

Khối lượng lớn — khuyến nghị chẻ thành 2 PR con nếu 1 người/agent làm:
`agentos-v2/m1-01-models-migration` → merge vào `agentos-v2/m1-identity-tenancy`,
`agentos-v2/m1-02-repo-scoping` → merge tiếp, rồi 1 PR tổng
`agentos-v2/m1-identity-tenancy` → `main`.

## Scope
**Trong phạm vi**: model `Organization/User/Membership/Role`, migration thêm
`org_id` vào toàn bộ bảng nghiệp vụ hiện có, data-migration backfill về 1 org
mặc định, base repository bắt buộc `org_id`.
**Ngoài phạm vi**: JWT/OAuth thật (M2), permission matrix/RBAC enforcement
(M3) — M1 chỉ tạo *data model* cho tenancy, chưa enforce quyền theo role.

## Depends on
M0 (CI phải xanh để tự tin migration không phá vỡ gì).

## Files to add
- `backend/app/models/organization.py`
- `backend/app/models/user.py`
- `backend/app/models/membership.py`
- `backend/app/models/role.py` (enum `Role`)
- `backend/alembic/versions/00XX_add_org_user_membership.py`
- `backend/alembic/versions/00XX_add_org_id_to_business_tables.py`
- `backend/alembic/versions/00XX_backfill_default_org.py` (hoặc gộp backfill
  logic vào migration trên qua `op.execute`/raw SQL trong `upgrade()`)
- `backend/alembic/versions/00XX_org_id_not_null.py`
- `backend/tests/test_multitenancy_migration.py`

## Files to modify
- `backend/app/models/agent.py, model.py, provider.py, mcp.py, workflow.py,
  session.py, message.py, usage.py, files.py, memory.py` — thêm cột
  `org_id: Mapped[str] = mapped_column(ForeignKey("organization.id"),
  nullable=True)` (tạm nullable, xem bước NOT NULL riêng) +
  `created_by_user_id: Mapped[str | None]`.
- `backend/app/repositories/base.py` — đổi signature hàm `list`/`get` (và
  mọi hàm con kế thừa) để **bắt buộc** nhận `org_id: str` làm tham số đầu,
  raise `TypeError` nếu gọi thiếu (không dùng default value ngầm để tránh
  quên).
- `backend/app/repositories/*.py` (mọi file) — cập nhật theo signature mới,
  thêm `.where(Model.org_id == org_id)` vào mọi query.
- `backend/app/dependencies.py` — thêm `get_current_org_id`.
- `backend/scripts/seed.py` — cập nhật để seed data gán vào 1 org mặc định
  (dùng cho dev/test, không phải migration production).

## Step-by-step
1. Viết 4 model mới, chạy `alembic revision --autogenerate -m "add org user membership"`.
   soát lại file autogenerate thủ công (autogenerate hay bỏ sót FK/index).
2. Viết migration thêm `org_id`/`created_by_user_id` (nullable) vào các bảng
   nghiệp vụ — **không** autogenerate 1 lần cho tất cả, viết tay để kiểm soát
   thứ tự và default value khi backfill.
3. Viết migration backfill: trong `upgrade()`, dùng raw SQL
   (`op.execute(text(...))` hoặc ORM session tạm) để: tạo 1 row
   `organization` ("Default Organization", slug `default`), 1 row `user` từ
   env `OPENAGENT_BOOTSTRAP_ADMIN_EMAIL`/`..._PASSWORD` (hash password ngay
   trong migration bằng `argon2` — thêm dependency sớm nếu M2 chưa làm), 1
   row `membership(role=owner)`, rồi `UPDATE <table> SET org_id = :default_org_id
   WHERE org_id IS NULL` cho từng bảng nghiệp vụ.
4. Migration cuối: `ALTER COLUMN org_id SET NOT NULL` cho từng bảng (chỉ
   chạy được sau khi chắc chắn backfill xong — thêm assertion trong
   `upgrade()`: query `COUNT(*) WHERE org_id IS NULL` phải = 0, nếu không thì
   raise để dừng migration thay vì âm thầm để lại NULL).
5. Sửa `base.py` + toàn bộ repository — chạy `pytest` để bắt hết chỗ gọi
   thiếu `org_id` (sẽ crash rõ ràng nhờ raise TypeError chủ động).
6. Viết test migration: dựng SQLite tạm, seed data kiểu "trước M1" (không có
   org_id), chạy `alembic upgrade head`, assert mọi row có `org_id` = default
   org.

## Suggested commit breakdown
1. `feat(agentos-m1): add organization, user, membership models`
2. `feat(agentos-m1): migration for org/user/membership tables`
3. `feat(agentos-m1): migration adding org_id to business tables (nullable)`
4. `feat(agentos-m1): backfill migration creating default org + owner user`
5. `feat(agentos-m1): migration enforcing org_id NOT NULL`
6. `refactor(agentos-m1): require org_id in base repository + all repos`
7. `feat(agentos-m1): add get_current_org_id dependency`
8. `test(agentos-m1): migration backfill test on pre-M1 seeded db`

## Tests to write
- `test_multitenancy_migration.py`: seed DB "kiểu cũ" (script raw insert
  không org_id) → `alembic upgrade head` → assert tất cả bảng có đúng 1 org,
  1 owner user, `Membership` đúng role.
- Cập nhật toàn bộ test hiện có gọi repository trực tiếp để truyền `org_id`
  (rà `backend/tests/*.py`, sẽ có nhiều chỗ cần sửa do signature đổi).
- `test_repository_scoping.py`: tạo 2 org, 2 agent (mỗi org 1 agent) → gọi
  `list(org_id=org_a)` không được trả agent của `org_b`.

## CI additions
Không cần job mới, nhưng đảm bảo `pytest` trong CI hiện có (M0) chạy migration
từ đầu trên DB sạch mỗi lần (không rely on DB đã tồn tại) — kiểm tra
`conftest.py` hiện tại có tự tạo DB tạm mỗi test run hay không, nếu chưa thì
thêm fixture.

## PR checklist
```
- [ ] Organization/User/Membership/Role model + migration tồn tại
- [ ] org_id + created_by_user_id đã thêm vào toàn bộ bảng nghiệp vụ liệt kê ở trên
- [ ] Migration backfill tạo đúng 1 Default Organization + 1 owner user từ env
- [ ] org_id NOT NULL sau backfill, có assertion chặn nếu backfill thiếu sót
- [ ] base repository bắt buộc org_id (raise nếu gọi thiếu), mọi repo con đã cập nhật
- [ ] test_multitenancy_migration.py pass trên DB seed kiểu cũ
- [ ] test_repository_scoping.py xác nhận cách ly dữ liệu giữa 2 org
- [ ] Toàn bộ pytest hiện có (kể cả test cũ phải sửa signature) pass
- [ ] CI xanh
```
