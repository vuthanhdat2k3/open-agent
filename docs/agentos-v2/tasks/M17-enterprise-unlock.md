# M17 — Mở khoá mua hàng doanh nghiệp

## Branch

`agentos-v2/m17-enterprise-unlock` từ `main`.

## Depends on

**M13** (nguồn dữ liệu cho toàn bộ phần compliance export).

## ⚠ Điều kiện khởi động

**KHÔNG bắt đầu milestone này khi chưa có khách hàng cụ thể yêu cầu.**

Đây là milestone duy nhất trong roadmap có điều kiện khởi động, vì:

- SAML/SCIM là code phức tạp, nhiều edge case theo từng IdP, và **không có
  người dùng nào cho tới khi có deal**. Xây sớm = code chết phải bảo trì.
- Yêu cầu compliance cụ thể khác nhau theo ngành và theo khách. Xây theo
  phỏng đoán gần như chắc chắn phải làm lại.

Khi khởi động, **chẻ nhỏ theo đúng thứ khách hàng yêu cầu**, đừng làm cả 4
phần bên dưới cùng lúc.

## Bốn phần độc lập (chọn theo nhu cầu thật)

### 17A — SAML 2.0 + SCIM provisioning

Tiêu chuẩn tối thiểu để qua vòng thẩm định của doanh nghiệp: SSO qua Okta /
Azure AD, cộng SCIM để tự động tạo/khoá tài khoản khi nhân sự vào/ra.

- Dùng thư viện có sẵn (`python3-saml` hoặc tương đương) — **không tự
  implement XML signature validation**, đó là chỗ sinh CVE.
- SCIM: `/scim/v2/Users`, `/scim/v2/Groups` map vào `User` + `Membership`
  đã có. Map SCIM group → `Role` phải khai báo tường minh, không đoán.
- Ghi audit cho mọi thay đổi do SCIM gây ra (`scim.user_provisioned`,
  `scim.user_deactivated`).

### 17B — Bộ hồ sơ tuân thủ (EU AI Act)

**Dữ liệu đã có sẵn từ M13** — phần này chỉ là truy vấn + xuất báo cáo, không
sinh dữ liệu mới. Đó là lý do M13 đáng làm trước.

| Điều | Yêu cầu | Nguồn dữ liệu |
|---|---|---|
| Điều 11 | Hồ sơ kỹ thuật | `AgentRelease` (cấu hình bất biến) + `EvaluationRun` (bằng chứng chất lượng) |
| Điều 12 | Nhật ký tự động | `audit_logs` (M13) + trace |
| Điều 14 | Giám sát của con người | `approval_requests` + audit approval |
| Điều 15 | Độ chính xác, mạnh mẽ | `EvaluationRun` theo thời gian |

- Endpoint `GET /api/compliance/evidence?from=&to=&agent_id=` → gói ZIP/JSON.
- **Cảnh báo cần ghi rõ trong tài liệu bàn giao**: xuất được bằng chứng
  ≠ tuân thủ. ISO 42001 chứng nhận *hệ thống quản lý của tổ chức*, EU AI Act
  quản lý *sản phẩm* — hai đối tượng khác nhau. OpenAgent cung cấp bằng
  chứng kỹ thuật, phần quy trình tổ chức là việc của khách hàng.

### 17C — Xuất audit log sang SIEM

- Sink cho Splunk HEC / Datadog Logs.
- Bất biến: chỉ append, có checksum chuỗi (mỗi row chứa hash của row trước)
  để phát hiện sửa xoá.
- Backpressure: SIEM chết thì buffer + retry, **không** được chặn đường chạy
  của agent.

### 17D — Bộ nhớ phân tầng (nóng / ấm / lạnh)

Thay `compactor.py` hiện tại (tóm tắt phần cũ + giữ 4 tin nhắn cuối).

| Tầng | Nội dung | Lưu ở |
|---|---|---|
| Nóng | N lượt gần nhất, nguyên văn | messages |
| Ấm | Tóm tắt cuộn, chi tiết vừa | `SessionMemory` |
| Lạnh | Nén sâu + recall ngữ nghĩa khi cần | `AgentMemory` + vector |

- Đây là phần **có lợi ích kỹ thuật độc lập với việc bán hàng** (giảm token,
  tăng chất lượng hội thoại dài) — nếu muốn làm sớm hơn M17, tách ra thành
  milestone riêng, đừng chờ deal.
- Phải đo được: so token/chi phí/pass-rate trước-sau bằng chính suite eval
  của M11/M15. Không đo thì không biết có tốt hơn không.

## Files (phác thảo — chi tiết hoá khi khởi động)

Chỉ liệt kê để ước lượng, **chưa phải đặc tả**:

- 17A: `backend/app/core/auth/saml.py`, `backend/app/api/v1/routes/scim.py`,
  `backend/app/models/saml_connection.py`
- 17B: `backend/app/compliance/evidence.py`,
  `backend/app/api/v1/routes/compliance.py`
- 17C: `backend/app/core/observability/siem.py`
- 17D: `backend/app/core/memory/tiers.py` (thay `compactor.py`)

## PR checklist (khung chung)

```
- [ ] Có yêu cầu khách hàng cụ thể làm căn cứ (ghi rõ trong PR description)
- [ ] Chỉ làm phần được yêu cầu, không làm cả 4 phần cùng lúc
- [ ] SAML dùng thư viện chín, KHÔNG tự implement XML signature validation
- [ ] SCIM group -> Role map khai báo tường minh, có audit
- [ ] Tài liệu compliance ghi rõ "bằng chứng kỹ thuật ≠ tuân thủ đầy đủ"
- [ ] SIEM sink không chặn đường chạy agent khi SIEM chết
- [ ] Bộ nhớ phân tầng có số đo trước-sau bằng eval suite, không chỉ "cảm giác tốt hơn"
- [ ] pytest xanh, CI xanh
```