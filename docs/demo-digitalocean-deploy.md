# Demo Deploy trên DigitalOcean — Hướng dẫn nhanh

Mục tiêu: deploy full stack OpenAgent (kể cả Zitadel SSO) lên 1 Droplet
DigitalOcean, có HTTPS thật qua Caddy + sslip.io, để demo cho người khác dùng
qua internet. Đây là bản rút gọn thao tác từ
[`deployment-runbook.md`](./deployment-runbook.md) — đọc file đó nếu cần giải
thích sâu hơn về từng biến môi trường hoặc kiến trúc.

## 1. Tạo Droplet

- Ubuntu 22.04/24.04, image marketplace có sẵn **Docker** (đỡ phải cài tay).
- Cấu hình tối thiểu cho demo mượt: **4 vCPU / 8 GB RAM** (Zitadel +
  ClickHouse của Langfuse ăn RAM nhiều nhất trong stack, không phải
  api/frontend). Có thể hạ xuống 4GB nếu bỏ `--profile identity` (dùng
  `OPENAGENT_AUTH_PROVIDER=local` thay Zitadel).
- Gán **Reserved IP** (không bắt buộc nhưng nên làm) nếu muốn IP không đổi
  khi phải rebuild droplet — domain sslip.io phụ thuộc vào IP này.
- Ghi lại IP public, ví dụ `203.0.113.10` (thay bằng IP thật của bạn trong
  toàn bộ hướng dẫn dưới).

## 2. Firewall

Qua DigitalOcean Cloud Firewall (control panel hoặc `doctl`), chỉ mở ra
internet:
- **22** (SSH)
- **80**, **443** (Caddy — ACME challenge + HTTPS)

Không mở 5433 (Postgres), 6379 (Redis), 6333 (Qdrant), 9000/9001 (MinIO),
8000 (api), 3000 (frontend) ra internet — chúng chỉ cần bind loopback trên
compose (đã hardening), firewall là lớp phòng thủ thứ 2, không phải thay thế.

## 3. Clone & cấu hình `.env`

```bash
ssh root@203.0.113.10
git clone git@github.com:vuthanhdat2k3/open-agent.git
cd open-agent && git checkout dev
cp .env.example .env
```

Sinh secret ngẫu nhiên nhanh:

```bash
openssl rand -hex 32   # JWT, crawler token, Redis password, Langfuse secrets (32 hex)
openssl rand -hex 16   # ZITADEL_MASTERKEY (cần đúng 32 ký tự)
openssl rand -hex 32   # LANGFUSE_ENCRYPTION_KEY cần 64 hex char -> dùng openssl rand -hex 32 (ra đúng 64 ký tự)
```

Điền vào `.env` — các biến KHÔNG có default an toàn, bắt buộc phải set:
`OPENAGENT_POSTGRES_PASSWORD`, `ZITADEL_POSTGRES_PASSWORD`,
`ZITADEL_MASTERKEY`, `ZITADEL_FIRSTINSTANCE_ORG_HUMAN_PASSWORD`,
`OPENAGENT_JWT_SECRET_KEY`, `CRAWLER_API_TOKEN`, `OPENAGENT_REDIS_PASSWORD`,
`MINIO_ROOT_USER`/`MINIO_ROOT_PASSWORD`, toàn bộ `LANGFUSE_*`.

Set thêm các biến production + domain (thay `203.0.113.10` bằng IP thật):

```env
OPENAGENT_RUNTIME=production
OPENAGENT_AUTH_PROVIDER=zitadel
OPENAGENT_COOKIE_SECURE=true

OPENAGENT_APP_DOMAIN=app.203.0.113.10.sslip.io
OPENAGENT_API_DOMAIN=api.203.0.113.10.sslip.io
OPENAGENT_AUTH_DOMAIN=auth.203.0.113.10.sslip.io
ZITADEL_DOMAIN=auth.203.0.113.10.sslip.io
ZITADEL_EXTERNALSECURE=true

NEXT_PUBLIC_API_BASE_URL=https://api.203.0.113.10.sslip.io
OPENAGENT_ZITADEL_ISSUER_URL=https://auth.203.0.113.10.sslip.io
OPENAGENT_ZITADEL_REDIRECT_URI=https://api.203.0.113.10.sslip.io/api/auth/callback
OPENAGENT_ZITADEL_POST_LOGOUT_REDIRECT_URI=https://app.203.0.113.10.sslip.io/
```

sslip.io không cần đăng ký gì — `<bất-kỳ>.<IP>.sslip.io` tự resolve về IP đó
qua DNS công khai, Let's Encrypt xác thực HTTP-01 challenge bình thường như
domain thật.

## 4. Build & lên stack

```bash
docker compose --env-file .env --profile identity --profile tls up -d --build --remove-orphans
docker compose --env-file .env ps                    # đợi tất cả "healthy"
docker compose --env-file .env logs caddy             # tìm dòng "certificate obtained successfully"
```

## 5. Bootstrap OAuth app trong Zitadel (làm 1 lần, thủ công)

1. Mở `https://auth.203.0.113.10.sslip.io`, đăng nhập bằng
   `zitadel-admin@zitadel.203.0.113.10.sslip.io` (hoặc theo
   `OPENAGENT_PLATFORM_ADMIN_EMAILS` bạn đã set) +
   `ZITADEL_FIRSTINSTANCE_ORG_HUMAN_PASSWORD` trong `.env`.
2. Console → tạo Project → tạo Application kiểu Web (Authorization Code +
   PKCE).
3. Redirect URI: `https://api.203.0.113.10.sslip.io/api/auth/callback`.
   Post-logout URI: `https://app.203.0.113.10.sslip.io/`.
4. Lấy `Project ID`, `Client ID`, `Client Secret` của app vừa tạo.
5. Tạo Personal Access Token cho user admin → dùng cho
   `OPENAGENT_ZITADEL_ADMIN_PAT`.
6. Điền 4 giá trị này vào `.env` trên droplet, rồi chỉ cần restart
   `api`/`worker` (không cần build lại frontend, các giá trị này không bake
   vào bundle):
   ```bash
   docker compose --env-file .env --profile identity --profile tls up -d api worker
   ```

## 6. Demo

Gửi link `https://app.203.0.113.10.sslip.io` cho người xem — HTTPS thật,
không cảnh báo trình duyệt, nhiều người dùng đồng thời, full chức năng
(chat, workflow, RAG, tools, login qua Zitadel...).

## 7. Dọn dẹp sau demo

Nếu chỉ demo tạm, **xoá droplet ngay sau khi xong** để không bị tính phí
tiếp — DigitalOcean tính theo giờ, xoá droplet dừng tính phí ngay (trừ phí
Reserved IP/snapshot nếu có tạo riêng, cũng nên xoá kèm).

```bash
doctl compute droplet delete <droplet-id>
```

---

## Phân tích chi phí (ước tính — tra giá chính thức trước khi đặt)

Lưu ý: công cụ tra giá real-time của tôi đang lỗi (thiếu API key search),
nên các số dưới đây là ước tính dựa trên cấu trúc giá Droplet phổ biến của
DigitalOcean tại thời điểm huấn luyện, **không phải giá live** — bạn nên mở
[digitalocean.com/pricing/droplets](https://www.digitalocean.com/pricing/droplets)
để xác nhận số chính xác hiện tại trước khi tạo droplet.

| Mục | Cấu hình | Ước tính giá/tháng | Ước tính giá/giờ |
|---|---|---|---|
| Droplet 8GB/4vCPU (Premium AMD/Intel) | Đủ chạy full stack + `identity` profile | ~$48–56/tháng | ~$0.07–0.08/giờ |
| Droplet 4GB/2vCPU | Nếu bỏ `--profile identity` (dùng auth local) | ~$24/tháng | ~$0.036/giờ |
| Bandwidth | DO tặng ~1-4TB outbound tuỳ plan, demo vài buổi không đáng lo | Thường nằm trong hạn mức miễn phí | — |
| Reserved IP | Miễn phí nếu đang gắn với droplet đang chạy; tính phí nhỏ nếu giữ IP mà không gắn droplet | ~$0 khi đang dùng | — |
| Let's Encrypt cert (qua Caddy) | Hoàn toàn miễn phí | $0 | $0 |
| Domain | Không cần — dùng sslip.io miễn phí | $0 | $0 |

**Điểm quan trọng nhất về chi phí**: DigitalOcean tính **theo giờ, prorated**,
không phải trả trước cả tháng. Nghĩa là:

- Tạo droplet, demo trong **2-3 giờ**, xoá ngay sau đó → chi phí thực tế chỉ
  khoảng **$0.15–0.25** (vài nghìn đồng), không phải cả tháng $48.
- Chi phí chỉ leo tới mức "/tháng" nếu bạn **để droplet chạy nguyên cả
  tháng** không xoá.
- Cách rẻ nhất để "thử deploy ngay bây giờ để test" đúng như bạn cần: tạo
  droplet, deploy, test xong trong buổi, **xoá droplet ngay** — tổng chi phí
  gần như không đáng kể (dưới 1 USD cho một buổi test vài giờ).

**So với Cloudflare Tunnel (buổi trước đã phân tích)**: Cloudflare Tunnel
$0 tuyệt đối nhưng cần máy cá nhân chạy suốt và domain không ổn định
(Quick Tunnel). DigitalOcean tốn một khoản rất nhỏ (~vài nghìn đồng cho vài
giờ test) nhưng đổi lại được domain/IP ổn định suốt vòng đời droplet, không
lo tunnel rớt giữa buổi demo làm gãy redirect URI của Zitadel — hợp hơn cho
yêu cầu "đảm bảo full chức năng" của bạn.

## Việc tôi KHÔNG thể tự làm

Tôi không có quyền tạo droplet, không có tài khoản DigitalOcean của bạn,
và không có SSH access vào máy demo (bạn chọn "máy khác/server riêng").
Toàn bộ các bước 1–6 phía trên cần bạn tự thực hiện. Nếu muốn tôi hỗ trợ
chạy trực tiếp thay vì làm tay, cung cấp một trong hai:

- **DigitalOcean API token** (Settings → API → Generate New Token) để tôi
  tạo droplet, cấu hình firewall qua `doctl`/API.
- **SSH access** (IP + private key hoặc user/password) tới droplet đã tạo
  sẵn, để tôi chạy các bước 3–5 trực tiếp trên đó.
