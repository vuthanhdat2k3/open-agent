"""Internal Docling REST adapter.

The pinned fork currently ships the converter/CLI but not docling-serve itself;
this keeps the service contract small and runs DocumentConverter in-process.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, UploadFile
from fastapi.responses import JSONResponse

app = FastAPI(title="OpenAgent Docling service")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/convert")
async def convert(file: UploadFile = File(...)) -> JSONResponse:
    from docling.document_converter import DocumentConverter

    converter_kwargs = {}
    if Path(file.filename or "").suffix.lower() == ".pdf" and os.environ.get(
        "DOCLING_OCR_ENGINE", "rapidocr"
    ).lower() == "rapidocr":
        from docling.datamodel.pipeline_options import PdfPipelineOptions, RapidOcrOptions
        from docling.datamodel.base_models import InputFormat
        from docling.document_converter import PdfFormatOption

        converter_kwargs["format_options"] = {
            InputFormat.PDF: PdfFormatOption(
                pipeline_options=PdfPipelineOptions(
                    do_ocr=True, ocr_options=RapidOcrOptions(backend="onnxruntime", lang=["en"])
                )
            )
        }

    suffix = Path(file.filename or "document").suffix or ".bin"
    with tempfile.NamedTemporaryFile(suffix=suffix) as handle:
        handle.write(await file.read())
        handle.flush()
        result = DocumentConverter(**converter_kwargs).convert(handle.name)
    return JSONResponse(
        {
            "text": result.document.export_to_markdown(),
            "metadata": {"filename": file.filename or "document"},
        }
    )
