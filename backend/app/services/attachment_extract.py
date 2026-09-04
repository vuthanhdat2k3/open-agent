from __future__ import annotations

import asyncio
import os

import httpx
import pdf_inspector
import structlog

from app.config import get_settings

logger = structlog.get_logger(__name__)

# ponytail: hard char cap keeps one attachment from blowing the prompt
# budget; raise if real usage needs longer documents inlined.
MAX_ATTACHMENT_PROMPT_CHARS = 20_000

_TEXT_EXTS = {".txt", ".md", ".csv", ".json", ".py", ".yaml", ".yml", ".html", ".htm"}


def is_extraction_error(text: str) -> bool:
    """Check if the extracted text indicates a failure message."""
    stripped = text.strip()
    return stripped.startswith("[could not read ") and stripped.endswith("]")


def _find_shared_lib(
    pkg_dir: str, matches: tuple[str, ...], exclude: tuple[str, ...] = ()
) -> str | None:
    try:
        names = os.listdir(pkg_dir)
    except OSError:
        return None
    for name in names:
        lower = name.lower()
        if any(x in lower for x in exclude):
            continue
        if any(m in lower for m in matches) and (
            lower.endswith((".dll", ".dylib")) or ".so" in lower
        ):
            return os.path.join(pkg_dir, name)
    return None


def _resolve_ocr_runtime_env() -> None:
    """Point pdf-inspector's OCR path at the PDFium/ONNX Runtime shared
    libraries bundled by the pypdfium2/onnxruntime wheels, so `pip install`
    is enough to enable OCR - no manual tarball download per pdf-inspector's
    own docs/ocr-runtime.md. An already-set env var always wins (ops can
    still pin a specific build); this only fills in what's missing, and
    quietly does nothing if the optional OCR deps aren't installed (native
    text-based PDF extraction works either way).
    """
    if "PDFIUM_LIB_PATH" not in os.environ:
        try:
            import pypdfium2_raw
        except ImportError:
            pass
        else:
            path = _find_shared_lib(os.path.dirname(pypdfium2_raw.__file__), ("pdfium",))
            if path:
                os.environ["PDFIUM_LIB_PATH"] = path

    if "ORT_DYLIB_PATH" not in os.environ:
        try:
            import onnxruntime
        except ImportError:
            pass
        else:
            capi_dir = os.path.join(os.path.dirname(onnxruntime.__file__), "capi")
            path = _find_shared_lib(capi_dir, ("onnxruntime",), exclude=("providers",))
            if path:
                os.environ["ORT_DYLIB_PATH"] = path


_resolve_ocr_runtime_env()


def _extract_pdf_sync(data: bytes, filename: str) -> str:
    """Synchronous CPU-bound PDF extraction using pdf-inspector (native and selective OCR)."""
    try:
        res = pdf_inspector.process_pdf_bytes(data)
        text = res.markdown or ""
        # If the PDF is classified as scanned/image_based or produced empty text,
        # fallback to intelligent selective OCR within pdf-inspector.
        if (not text.strip() or res.pdf_type in ("scanned", "image_based")) and hasattr(
            pdf_inspector, "process_pdf_with_ocr_bytes"
        ):
            try:
                ocr_res = pdf_inspector.process_pdf_with_ocr_bytes(data)
                text = ocr_res.markdown or ""
            except Exception as ocr_exc:
                ocr_err = str(ocr_exc).strip() or type(ocr_exc).__name__
                logger.warning(
                    "pdf_ocr_extraction_failed",
                    filename=filename,
                    error=ocr_err,
                )
        if not text.strip():
            return f"[could not read '{filename}': PDF contains no extractable text]"
        return text
    except Exception as exc:
        err_msg = str(exc).strip() or type(exc).__name__
        logger.error("pdf_extraction_failed", filename=filename, error=err_msg)
        return f"[could not read '{filename}': {err_msg}]"


async def extract_text(data: bytes, filename: str) -> str:
    """Best-effort plain-text extraction to inline a chat attachment into the
    prompt for this turn only. Never writes to the RAG index — ingestion is a
    separate, explicit action (rag_ingest_file / POST /api/files/{id}/ingest).
    """
    ext = os.path.splitext(filename)[1].lower()
    if ext in _TEXT_EXTS:
        text = data.decode("utf-8", errors="replace")
    elif ext == ".pdf":
        # PDFs are processed exclusively in-process using pdf-inspector (Rust/C++).
        # Run in thread pool to avoid blocking the async event loop.
        text = await asyncio.to_thread(_extract_pdf_sync, data, filename)
    else:
        # Office and other document formats route to the external docling-service.
        settings = get_settings()
        if not settings.docling_service_url:
            return f"[could not read '{filename}': document extraction service is not configured]"
        try:
            async with httpx.AsyncClient(timeout=90.0) as client:
                resp = await client.post(
                    f"{settings.docling_service_url.rstrip('/')}/convert",
                    files={"file": (filename, data, "application/octet-stream")},
                )
                resp.raise_for_status()
                payload = resp.json()
        except httpx.ReadTimeout:
            logger.error("docling_read_timeout", filename=filename)
            return f"[could not read '{filename}': conversion timed out after 90s]"
        except (httpx.HTTPError, ValueError) as exc:
            err_msg = str(exc).strip() or type(exc).__name__
            logger.error("docling_conversion_failed", filename=filename, error=err_msg)
            return f"[could not read '{filename}': {err_msg}]"
        except Exception as exc:
            err_msg = str(exc).strip() or type(exc).__name__
            logger.error("docling_unexpected_error", filename=filename, error=err_msg)
            return f"[could not read '{filename}': {err_msg}]"

        text = payload.get("text")
        if not isinstance(text, str):
            return f"[could not read '{filename}': extraction service returned no text]"

    if len(text) > MAX_ATTACHMENT_PROMPT_CHARS:
        text = text[:MAX_ATTACHMENT_PROMPT_CHARS] + "\n...[truncated]"
    return text
