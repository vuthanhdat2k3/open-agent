# M2 — AuthN (OAuth2/OIDC + JWT + API key)

## Branch
`agentos-v2/m2-authn` từ `main` (sau khi M1 merge).

## Scope
**Trong phạm vi**: đăng ký/đăng nhập email+password, JWT access+refresh
(rotation), OAuth Google/GitHub, API key cho machine access, route
`auth.py` + `orgs.py` (member management cơ bản — invite/list/change
role/remove, nhưng **không** enforce permission matrix, đó là M3).
**Ngoài phạm vi**: permission check theo role (M3 mới enforce — M2 chỉ cần
`get_current_user` trả đúng user, chưa cần `require_permission`).

## Depends on
M1 (cần `User`, `Membership`, `Organization` model đã có).

## Files to add
- `backend/app/models/oauth_account.py`
- `backend/app/models/refresh_token.py`
- `backend/app/models/api_key.py`
- `backend/app/core/auth/jwt.py`
- `backend/app/core/auth/password.py`
- `backend/app/core/auth/oauth.py`
- `backend/app/core/auth/api_key.py`
- `backend/app/api/v1/routes/auth.py`
- `backend/app/api/v1/routes/orgs.py`
- `backend/app/schemas/auth.py` (request/response: `RegisterRequest,
  LoginRequest, TokenResponse, MeResponse, InviteMemberRequest,
  ApiKeyCreateResponse` — chỉ trả full key 1 lần lúc tạo)
- `backend/alembic/versions/00XX_add_oauth_refresh_apikey.py`
- `backend/tests/test_auth.py`

## Files to modify
- `backend/pyproject.toml` — thêm `authlib`, `pyjwt` (hoặc
  `python-jose[cryptography]`), `argon2-cffi`.
- `backend/app/config.py` — thêm `jwt_private_key_path`,
  `jwt_public_key_path` (hoặc key trực tiếp qua env cho dev),
  `jwt_access_ttl_minutes=15`, `jwt_refresh_ttl_days=30`,
  `oauth_google_client_id/secret`, `oauth_github_client_id/secret`,
  `cookie_secure: bool = True` (false chỉ cho dev local).
- `backend/app/dependencies.py` — thêm `get_current_user` (thử JWT trước,
  fallback `X-API-Key` header → `api_key` table), giữ nguyên
  `verify_api_key` cũ (không xoá, vẫn dùng cho machine/dev mode nếu
  `OPENAGENT_API_KEY` được set).
- `backend/app/api/v1/router.py` — mount `auth.py`, `orgs.py`.

## Step-by-step
1. Sinh cặp khoá JWT (RS256 hoặc Ed25519) — script 1 lần
   `backend/scripts/gen_jwt_keys.py`, output vào `.env`/file, **không commit
   key thật vào git** (thêm vào `.gitignore` nếu output ra file).
2. `core/auth/password.py`: `hash_password`, `verify_password` (argon2id).
3. `core/auth/jwt.py`: `create_access_token(user_id, org_id, role) ->str`,
   `create_refresh_token() -> (raw, hash)`, `verify_access_token(token) ->
   claims`.
4. Route `POST /auth/register`: tạo `User` + `Organization` mới (org tên mặc
   định = email hoặc do user đặt) + `Membership(role=owner)` — người đăng ký
   luôn là owner của org họ tự tạo.
5. Route `POST /auth/login`: verify password, issue access token (JSON body)
   + refresh token (httponly, `Secure`, `SameSite=Lax` cookie).
6. Route `POST /auth/refresh`: verify refresh cookie, kiểm `revoked_at IS
   NULL`, revoke token cũ (`revoked_at=now`), issue cặp mới, set
   `replaced_by_id`.
7. Route `POST /auth/logout`: revoke refresh token hiện tại.
8. `core/auth/oauth.py` + route callback: dùng `authlib` `OAuth` client,
   redirect flow chuẩn; khi callback thành công, tìm/tạo `User` +
   `OAuthAccount` theo `(provider, provider_account_id)`; nếu email đã tồn
   tại từ đăng ký thường → link account (không tạo user trùng).
9. `core/auth/api_key.py`: generate `oa_live_<base62 32 bytes>`, hash SHA-256
   trước khi lưu; route `POST /orgs/{id}/api-keys` trả full key 1 lần, `GET`
   chỉ trả `key_prefix` + metadata, `DELETE` set `revoked_at`.
10. `orgs.py`: `POST /orgs`, `GET /orgs/{id}/members`, `POST
    /orgs/{id}/members` (invite theo email — nếu user chưa tồn tại, tạo
    pending invite record đơn giản hoặc yêu cầu họ đăng ký trước rồi mới
    thêm — chọn phương án đơn giản: invite chỉ hoạt động nếu email đã có
    `User`, ghi rõ giới hạn này trong docstring route).

## Suggested commit breakdown
1. `feat(agentos-m2): add oauth_account, refresh_token, api_key models + migration`
2. `feat(agentos-m2): jwt + password hashing core module`
3. `feat(agentos-m2): register/login/refresh/logout routes`
4. `feat(agentos-m2): refresh token rotation with revocation`
5. `feat(agentos-m2): google/github oauth login`
6. `feat(agentos-m2): api key generation + management routes`
7. `feat(agentos-m2): org creation + member list/invite/remove routes`
8. `feat(agentos-m2): get_current_user dependency (jwt + api key fallback)`
9. `test(agentos-m2): auth flow integration tests`

## Tests to write
- `test_auth.py::test_register_login_me` — full flow trả đúng user.
- `test_auth.py::test_refresh_rotation_rejects_old_token` — dùng refresh
  token đã rotate → phải bị từ chối (401), đây là test bảo mật quan trọng
  nhất của milestone này, không được bỏ qua.
- `test_auth.py::test_login_wrong_password_401`.
- `test_auth.py::test_api_key_full_value_shown_once` — `GET` sau khi tạo
  không được trả full key, chỉ prefix.
- `test_auth.py::test_oauth_callback_links_existing_email` (mock provider
  response, không gọi Google/GitHub thật trong CI).

## CI additions
Thêm secret giả trong CI env (`JWT_PRIVATE_KEY_TEST`, ...) qua GitHub Actions
`env:` block trong job `backend` — không dùng secret thật, sinh keypair test
ngay trong step CI trước khi chạy pytest (`run: python backend/scripts/gen_jwt_keys.py --out /tmp/test_keys`).

## PR checklist
```
- [ ] Register/login/me hoạt động end-to-end
- [ ] Refresh token rotate đúng, token cũ dùng lại bị từ chối (test bắt buộc pass)
- [ ] OAuth Google/GitHub callback tạo/link User đúng (test dùng mock, không gọi provider thật)
- [ ] API key chỉ hiện full value 1 lần lúc tạo
- [ ] verify_api_key (machine mode) cũ vẫn hoạt động, không bị xoá/phá vỡ
- [ ] Không JWT private key nào commit vào git (kiểm tra git status/diff trước PR)
- [ ] pytest xanh, CI xanh
```
