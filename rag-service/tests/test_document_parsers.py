from __future__ import annotations

import io
import sys
import types

import pytest
from PIL import Image, ImageDraw
from pypdf import PdfReader, PdfWriter


def _text_pdf() -> bytes:
    # Minimal valid PDF with a text layer, used as a stable routing snapshot.
    objects = [
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n",
        b"2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj\n",
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 320 80]/Resources<</Font<</F1 6 0 R>>>>/Contents 4 0 R>>endobj\n",
        b"4 0 obj<</Length 43>>stream\nBT /F1 12 Tf 10 40 Td (TEXT SNAPSHOT) Tj ET\nendstream\nendobj\n",
        b"5 0 obj<</Producer(OpenAgent)>>endobj\n",
        b"6 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n",
    ]
    output = io.BytesIO(b"%PDF-1.4\n")
    offsets = []
    for obj in objects:
        offsets.append(output.tell())
        output.write(obj)
    start = output.tell()
    output.write(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    output.write(b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets))
    output.write(f"trailer<</Size {len(objects) + 1}/Root 1 0 R>>\nstartxref\n{start}\n%%EOF".encode())
    return output.getvalue()


def _image_pdf() -> bytes:
    image = Image.new("RGB", (320, 80), "white")
    ImageDraw.Draw(image).text((10, 20), "SCAN SNAPSHOT", fill="black")
    image_bytes = io.BytesIO()
    image.save(image_bytes, format="PNG")
    writer = PdfWriter()
    page = writer.add_blank_page(width=320, height=80)
    page.images  # force pypdf image API availability check
    page.merge_page(PdfReader(io.BytesIO(_one_page_image_pdf(image_bytes.getvalue()))).pages[0])
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def _one_page_image_pdf(png: bytes) -> bytes:
    # pypdf cannot create an image page by itself; use a compact PDF image
    # object with a Flate-decoded RGB stream generated from the PNG pixels.
    image = Image.open(io.BytesIO(png)).convert("RGB")
    raw = image.tobytes()
    import zlib

    stream = zlib.compress(raw)
    objects = [
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n",
        b"2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj\n",
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 320 80]/Resources<</XObject<</Im1 4 0 R>>>>/Contents 5 0 R>>endobj\n",
        f"4 0 obj<</Type/XObject/Subtype/Image/Width 320/Height 80/ColorSpace/DeviceRGB/BitsPerComponent 8/Filter/FlateDecode/Length {len(stream)}>>stream\n".encode() + stream + b"\nendstream\nendobj\n",
        b"5 0 obj<</Length 34>>stream\nq 320 0 0 80 0 0 cm /Im1 Do Q\nendstream\nendobj\n",
    ]
    output = io.BytesIO(b"%PDF-1.4\n")
    offsets = []
    for obj in objects:
        offsets.append(output.tell())
        output.write(obj)
    start = output.tell()
    output.write(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    output.write(b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets))
    output.write(f"trailer<</Size {len(objects) + 1}/Root 1 0 R>>\nstartxref\n{start}\n%%EOF".encode())
    return output.getvalue()


def _fake_inspector(monkeypatch, pdf_type: str, confidence: float = 0.99) -> None:
    monkeypatch.setitem(
        sys.modules,
        "pdf_inspector",
        types.SimpleNamespace(
            classify_pdf_bytes=lambda _: types.SimpleNamespace(
                pdf_type=pdf_type, confidence=confidence
            )
        ),
    )


@pytest.mark.asyncio
async def test_text_pdf_snapshot_keeps_native_parser(monkeypatch):
    _fake_inspector(monkeypatch, "text_based")
    monkeypatch.delenv("DOCLING_SERVICE_URL", raising=False)
    from rag_service.pipeline.parser.pdf import PDFParser

    result = await PDFParser().parse(_text_pdf())
    assert result.metadata["pdf_classification"] == "text_based"
    assert result.metadata["page_count"] == 1
    assert "TEXT SNAPSHOT" in result.text
    assert "warnings" not in result.metadata


@pytest.mark.asyncio
async def test_scanned_pdf_snapshot_routes_and_warns_on_unavailable_service(monkeypatch):
    _fake_inspector(monkeypatch, "scanned")
    monkeypatch.setenv("DOCLING_SERVICE_URL", "http://docling")
    from rag_service.pipeline.parser.pdf import PDFParser

    result = await PDFParser().parse(_image_pdf())
    assert result.metadata["pdf_classification"] == "scanned"
    assert result.metadata["warnings"] == [
        "scanned PDF, OCR service unavailable; text may be incomplete"
    ]


@pytest.mark.asyncio
async def test_pptx_snapshot_uses_docling(monkeypatch):
    from rag_service.pipeline.parser import pptx

    async def fake_parse(source: bytes, filename: str):
        assert filename == "document.pptx"
        return "# Slide snapshot", {"page_count": 1}

    monkeypatch.setattr(pptx, "parse_with_docling", fake_parse)
    result = await pptx.PPTXParser().parse(b"pptx fixture")
    assert result.text == "# Slide snapshot"
    assert result.metadata["parser"] == "docling"
