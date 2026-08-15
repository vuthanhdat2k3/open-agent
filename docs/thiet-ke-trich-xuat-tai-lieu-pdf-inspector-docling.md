# Thiết kế: Đọc file, trích xuất text và OCR bằng pdf-inspector + Docling

Date: 2026-08-15
Status: Draft — chờ review trước khi triển khai
Repo đã fork:
- https://github.com/vuthanhdat2k3/pdf-inspector (từ `firecrawl/pdf-inspector`, MIT)
- https://github.com/vuthanhdat2k3/docling (từ `docling-project/docling`, MIT)

## 1. Bối cảnh

Spec trước (`docs/thiet-ke-hoan-thien-du-an-cuoi-khoa-openagent.md` mục 13) đã kết luận: PDF/DOCX hiện có parser đủ dùng (`pypdf`/`pdfminer.six`, `python-docx`), nhưng có 2 khoảng trống thật:

1. Không phát hiện được PDF scan (ảnh, không có text layer) — `pypdf`/`pdfminer` âm thầm trả text rỗng thay vì báo rõ.
2. Không có OCR, không hỗ trợ PPTX, và `pypdf` chỉ lấy text thô của PDF — mất cấu trúc bảng.

Người dùng quyết định đóng cả hai bằng cách fork và tự chủ 2 công cụ chuyên trách thay vì tự viết hoặc phụ thuộc trực tiếp bản gốc trên PyPI. Spec này thiết kế cách tích hợp.

## 2. Vì sao fork thay vì `pip install` thẳng từ PyPI

- Cả hai đang phát triển nhanh (`docling` 64.7k sao, cập nhật liên tục) — fork tại 1 commit cụ thể cho pin version tuyệt đối, reproducible build, tránh một bản release PyPI mới của upstream đổi hành vi/breaking change ngoài kiểm soát.
- Có quyền patch riêng nếu cần (ví dụ giới hạn OCR engine, bớt input format không cần, vá lỗ hổng trước khi upstream release).
- Vẫn theo dõi được upstream để sync định kỳ (fork giữ nguyên lịch sử, `git fetch upstream` bình thường).
- Cả hai MIT license — fork và dùng nội bộ không có ràng buộc pháp lý.

## 3. Vai trò của từng công cụ (không chồng lấn)

| | pdf-inspector | Docling |
|---|---|---|
| Loại | Rust, native, cực nhẹ, không ML model | Python, nặng (layout model, OCR model) |
| Việc làm | Phân loại PDF: `TextBased`/`Scanned`/`ImageBased`/`Mixed` + confidence per-page | Trích xuất đầy đủ: layout, table structure, OCR, xuất Markdown/JSON |
| OCR | Không tự OCR — chỉ phát hiện khi nào cần | Có OCR built-in (nhiều engine) |
| Khi nào gọi | Luôn luôn, bước đầu tiên trước khi xử lý bất kỳ PDF nào — rẻ, nhanh | Chỉ khi pdf-inspector báo `Scanned`/`ImageBased`/`Mixed`, hoặc cần table structure PDF, hoặc file là PPTX |

Không dùng Docling để thay `python-docx`/`openpyxl` cho DOCX/XLSX thường — hai định dạng đó luôn có text layer sẵn (native Office format), không cần OCR, và `python-docx` đã trích được heading + table đủ tốt cho nhu cầu hiện tại. Dùng Docling đúng chỗ nó có giá trị riêng biệt: OCR, PPTX, table structure của PDF.

## 4. Kiến trúc triển khai

pdf-inspector — chạy in-process trong `rag-service` (không cần container riêng). Rust có Python binding qua PyPI dạng wheel; cài như dependency Python bình thường, gọi trực tiếp trong `pipeline/parser/pdf.py`.

Docling — chạy như service riêng, tách container, cùng mẫu với `crawl4ai` (đã có trong `docker-compose.yml` cho `web_fetch`, xem `docs/superpowers/specs/2026-08-09-web-search-revamp-design.md`): heavy dependency (layout model + OCR model), không nên nhét vào cùng image với `rag-service` (image `rag-service` hiện nhẹ, khởi động nhanh — không nên làm nặng nó vì một luồng ít khi cần OCR).

```text
docker-compose.yml
├── rag-service          — nhẹ, có pdf-inspector in-process
├── docling-service       — MỚI, image riêng, build từ fork tại commit cố định
│                           expose docling-serve (REST) hoặc MCP server nội bộ
│                           internal-network only, không host port
└── crawl4ai              — (đã có) mẫu tham khảo cho container OCR/heavy-processing
```

Docling hỗ trợ sẵn chế độ chạy `docling-serve` (REST API) hoặc MCP server — dùng thẳng, không tự viết wrapper.

## 5. Luồng xử lý PDF (routing)

```text
PDF bytes vào pipeline/parser/pdf.py
  → pdf-inspector.classify(bytes)
      TextBased (confidence cao)
        → pypdf/pdfminer.six hiện tại (nhanh, rẻ, không đổi)
      Scanned | ImageBased | Mixed | confidence thấp
        → gọi docling-service (OCR + layout + table structure)
        → docling-service không khả dụng/lỗi/timeout
            → fallback: vẫn thử pypdf (may empty), trả ParseResult
              kèm warning rõ ràng "scanned PDF, OCR service unavailable,
              text may be incomplete" — KHÔNG âm thầm trả rỗng
```

Đây là cùng pattern fail-open-with-explicit-warning đã dùng cho SearXNG→DDG và crawl4ai→httpx trong web-search-revamp — nhất quán với nguyên tắc "không fake dữ liệu khi thiếu" xuyên suốt dự án.

## 6. Thay đổi cụ thể trong `rag-service`

### 6.1 `pipeline/parser/pdf.py`

```python
async def parse(self, source: bytes | str, **kwargs: object) -> ParseResult:
    ...
    classification = _classify_pdf(source)   # pdf-inspector, try/except ImportError -> None
    if classification is not None and classification.category in ("scanned", "image_based", "mixed"):
        try:
            return await _parse_via_docling(source)
        except (DoclingServiceError, TimeoutError) as exc:
            logger.warning("docling_unavailable_falling_back", error=str(exc))
            # rơi xuống nhánh pypdf/pdfminer hiện tại, KHÔNG raise — nhưng gắn warning vào metadata
    # nhánh pypdf/pdfminer hiện tại giữ nguyên
```

`classification=None` (thiếu pdf-inspector hoặc lỗi) → coi như `TextBased`, đi thẳng nhánh hiện tại — giữ đúng hành vi ngày hôm nay khi không cấu hình gì thêm.

### 6.2 `pipeline/parser/docling_client.py` (mới)

Gọi `docling-service` qua HTTP (REST của `docling-serve`), timeout ngắn, không giữ connection lâu — theo đúng pattern gọi `crawl4ai` đã có.

### 6.3 `pipeline/parser/pptx.py` (mới)

PPTX hiện chưa có parser nào. Dùng Docling luôn (không cần pdf-inspector vì PPTX không có khái niệm "scanned") — route trực tiếp mọi file `.pptx` sang `docling-service`.

### 6.4 Cấu hình — mặc định tắt, opt-in

```text
DOCLING_SERVICE_URL=          # rỗng mặc định — PDF scan/PPTX trả warning "OCR not configured" thay vì lỗi
                               # đặt giá trị khi deploy docling-service
DOCLING_OCR_ENGINE=rapidocr    # mặc định RapidOCR (ONNX, không cần GPU/torch nặng)
                               # thay vì EasyOCR mặc định của Docling để giữ image nhẹ hơn — cần
                               # xác nhận lại lựa chọn engine cụ thể khi implement (mục 9)
```

Không bật OCR mặc định cho mọi deployment hiện có — giữ nguyên hành vi zero-config, giống cách `SEARXNG_URL`/`CRAWLER_API_TOKEN` đã opt-in trong spec trước.

## 7. Bảo trì fork

- Đặt `upstream` remote trỏ về repo gốc (`firecrawl/pdf-inspector`, `docling-project/docling`) trên cả hai fork để `git fetch upstream` định kỳ.
- Build image từ commit SHA cố định trên fork (không theo branch mặc định của fork, tránh trôi version ngoài ý muốn khi ai đó lỡ sync).
- Quy trình cập nhật: fetch upstream → review changelog → merge vào 1 branch riêng trên fork (`sync/<date>`) → build/test → mới đổi SHA pin trong `docker-compose.yml`/`pyproject.toml`. Không tự động sync.

## 8. Acceptance criteria

- PDF có text layer (đa số case hiện tại): hành vi không đổi, không có độ trễ thêm đáng kể từ bước classify (pdf-inspector là native code, mili-giây).
- PDF scan (ảnh) với `docling-service` khả dụng: trả text đọc được qua OCR, không còn rỗng.
- PDF scan khi `docling-service` tắt/lỗi: trả `ParseResult` có `warnings: ["scanned PDF, OCR unavailable"]`, không giả vờ thành công.
- File `.pptx`: parse được nội dung slide (text), trước đây không hỗ trợ.
- Test snapshot: 1 PDF text-based, 1 PDF scan giả lập (ảnh nhúng, không text layer), 1 PPTX mẫu.
- Không đổi hành vi DOCX/XLSX hiện có (Docling không được gọi cho hai định dạng này).

## 9. Rủi ro và điểm cần xác nhận khi implement

| Rủi ro | Ghi chú |
|---|---|
| Wheel `pdf-inspector` (Rust/PyO3) có sẵn cho đúng platform Docker image (Python version, glibc/musl) không | Cần verify lúc build image; nếu không có wheel sẵn, build từ source trong multi-stage Dockerfile (cần toolchain Rust ở build stage) |
| `docling-service` kéo theo dependency nặng (layout model, OCR model) → image lớn, thời gian cold-start lâu | Chạy container riêng (mục 4), không ảnh hưởng `rag-service`; đặt resource limit + healthcheck riêng |
| Chọn OCR engine (RapidOCR vs EasyOCR vs Tesseract) ảnh hưởng độ chính xác và kích thước image | RapidOCR đề xuất làm mặc định (ONNX, không cần torch) nhưng cần benchmark thực tế trên vài PDF tiếng Việt/tiếng Anh trước khi chốt — đồ án capstone không yêu cầu OCR nên đây không phải việc gấp |
| Fork lệch dần khỏi upstream nếu không sync đều | Quy trình sync định kỳ ở mục 7, không tự động — cần người phụ trách |
| Docling xử lý PDF scan có thể chậm (giây, không phải mili-giây) | Không nằm trên đường HTTP request đồng bộ — nếu dùng cho CI/RAG ingest, chạy qua job queue (arq) đã có sẵn trong hệ thống, không gọi trực tiếp trong request handler |

## 10. Ngoài phạm vi (chưa làm ở bước này)

- Video/audio input formats mà Docling hỗ trợ (MP4, MP3, WAV, WebVTT...) — không có nhu cầu hiện tại trong đồ án hay hệ thống, không tích hợp.
- Tự train/fine-tune model layout/OCR — dùng nguyên model mặc định của Docling.
- GPU acceleration cho OCR — mặc định chạy CPU, chỉ cân nhắc GPU nếu benchmark cho thấy CPU quá chậm cho khối lượng thực tế.

## 11. Tham chiếu

- https://github.com/vuthanhdat2k3/pdf-inspector (fork) / https://github.com/firecrawl/pdf-inspector (upstream)
- https://github.com/vuthanhdat2k3/docling (fork) / https://github.com/docling-project/docling (upstream)
- `rag-service/rag_service/pipeline/parser/{pdf,docx}.py` — parser hiện có, điểm tích hợp.
- `docs/superpowers/specs/2026-08-09-web-search-revamp-design.md` — mẫu kiến trúc self-hosted service + fallback (crawl4ai) đã áp dụng lại ở đây.
- `docs/thiet-ke-hoan-thien-du-an-cuoi-khoa-openagent.md` mục 13 — phân tích ban đầu dẫn tới quyết định fork.
