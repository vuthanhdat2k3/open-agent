from __future__ import annotations

import io
from unittest.mock import MagicMock, patch

import httpx
import pytest
from xhtml2pdf import pisa

from app.services.attachment_extract import (
    MAX_ATTACHMENT_PROMPT_CHARS,
    extract_text,
    is_extraction_error,
)


def _generate_test_pdf(text: str) -> bytes:
    buf = io.BytesIO()
    pisa.CreatePDF(f"<html><body><h1>{text}</h1></body></html>", dest=buf)
    return buf.getvalue()


def _generate_scanned_pdf(text: str) -> bytes:
    """A PDF with the given text baked into a raster image, no text layer -
    same shape as a real scanned document, to exercise the real (unmocked)
    PDFium + ONNX Runtime OCR path end to end."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (500, 120), color="white")
    ImageDraw.Draw(img).text((10, 40), text, fill="black")
    buf = io.BytesIO()
    img.save(buf, format="PDF")
    return buf.getvalue()


@pytest.mark.asyncio
async def test_extract_text_pdf_real_ocr_end_to_end() -> None:
    """No mocks: regression guard for the PDFium/ONNX Runtime shared-library
    auto-resolution in attachment_extract.py - a scanned PDF must actually
    OCR successfully, not silently degrade to "no extractable text"."""
    pdf_bytes = _generate_scanned_pdf("HELLO OCR TEST 12345")
    extracted = await extract_text(pdf_bytes, "scanned.pdf")
    assert not is_extraction_error(extracted)
    assert "HELLO OCR TEST 12345" in extracted


@pytest.mark.asyncio
async def test_extract_text_plain_formats() -> None:
    txt_data = b"Hello world, plain text!"
    assert await extract_text(txt_data, "notes.txt") == "Hello world, plain text!"

    md_data = b"# Markdown Title\nContent"
    assert await extract_text(md_data, "readme.md") == "# Markdown Title\nContent"

    json_data = b'{"key": "value"}'
    assert await extract_text(json_data, "data.json") == '{"key": "value"}'


@pytest.mark.asyncio
async def test_extract_text_pdf_native_pdf_inspector() -> None:
    pdf_bytes = _generate_test_pdf("Quarterly Financial Report")
    extracted = await extract_text(pdf_bytes, "financials.pdf")

    assert "Quarterly Financial Report" in extracted
    assert not is_extraction_error(extracted)


@pytest.mark.asyncio
async def test_extract_text_pdf_ocr_fallback() -> None:
    mock_pdf_result = MagicMock()
    mock_pdf_result.pdf_type = "scanned"
    mock_pdf_result.markdown = ""

    mock_ocr_result = MagicMock()
    mock_ocr_result.markdown = "Scanned document text from OCR"

    with (
        patch("pdf_inspector.process_pdf_bytes", return_value=mock_pdf_result),
        patch("pdf_inspector.process_pdf_with_ocr_bytes", return_value=mock_ocr_result),
    ):
        extracted = await extract_text(b"%PDF-fake-scanned", "scanned_doc.pdf")
        assert extracted == "Scanned document text from OCR"
        assert not is_extraction_error(extracted)


@pytest.mark.asyncio
async def test_extract_text_pdf_empty_ocr_fallback() -> None:
    mock_pdf_result = MagicMock()
    mock_pdf_result.pdf_type = "image_based"
    mock_pdf_result.markdown = ""

    mock_ocr_result = MagicMock()
    mock_ocr_result.markdown = ""

    with (
        patch("pdf_inspector.process_pdf_bytes", return_value=mock_pdf_result),
        patch("pdf_inspector.process_pdf_with_ocr_bytes", return_value=mock_ocr_result),
    ):
        extracted = await extract_text(b"%PDF-fake-empty", "empty.pdf")
        assert is_extraction_error(extracted)
        assert "PDF contains no extractable text" in extracted


@pytest.mark.asyncio
async def test_extract_text_pdf_error_never_empty_message() -> None:
    class EmptyException(Exception):
        def __str__(self) -> str:
            return ""

    with patch("pdf_inspector.process_pdf_bytes", side_effect=EmptyException()):
        extracted = await extract_text(b"%PDF-bad", "broken.pdf")
        assert is_extraction_error(extracted)
        assert extracted == "[could not read 'broken.pdf': EmptyException]"
        assert not extracted.endswith(": ]")


@pytest.mark.asyncio
async def test_extract_text_docling_read_timeout_clear_message() -> None:
    with patch("app.config.get_settings") as mock_settings:
        mock_settings.return_value.docling_service_url = "http://docling-service:8080"
        with patch("httpx.AsyncClient.post", side_effect=httpx.ReadTimeout("timed out")):
            extracted = await extract_text(b"fake-docx-data", "contract.docx")
            assert is_extraction_error(extracted)
            assert "conversion timed out after 90s" in extracted


@pytest.mark.asyncio
async def test_extract_text_docling_empty_error_fallback() -> None:
    class EmptyHTTPError(httpx.HTTPError):
        def __init__(self) -> None:
            super().__init__("")

    with patch("app.config.get_settings") as mock_settings:
        mock_settings.return_value.docling_service_url = "http://docling-service:8080"
        with patch("httpx.AsyncClient.post", side_effect=EmptyHTTPError()):
            extracted = await extract_text(b"fake-docx-data", "contract.docx")
            assert is_extraction_error(extracted)
            assert extracted == "[could not read 'contract.docx': EmptyHTTPError]"
            assert not extracted.endswith(": ]")


@pytest.mark.asyncio
async def test_extract_text_truncation_cap() -> None:
    long_text = "A" * (MAX_ATTACHMENT_PROMPT_CHARS + 500)
    data = long_text.encode("utf-8")
    extracted = await extract_text(data, "large.txt")
    assert len(extracted) > MAX_ATTACHMENT_PROMPT_CHARS
    assert extracted.endswith("\n...[truncated]")
    assert extracted.startswith("A" * 100)
