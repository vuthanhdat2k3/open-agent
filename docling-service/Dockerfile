# Docling service pinned to the reviewed fork commit, not a floating branch.
FROM python:3.11-slim-bookworm

# RapidOCR/ONNX is the default: CPU-friendly and avoids EasyOCR's OCR torch
# stack. Docling's standard bundle still needs torch for layout/table models,
# so explicitly use the CPU wheel index to avoid pulling CUDA binaries.
ARG DOCLING_COMMIT=61d76f1ff3f8428065465889f7b4577da7df704c
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl libgl1 libglib2.0-0 git && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    "docling-slim[standard] @ git+https://github.com/vuthanhdat2k3/docling.git@${DOCLING_COMMIT}" \
    "fastapi>=0.110,<1.0" "uvicorn[standard]>=0.29,<1.0" "python-multipart>=0.0.9,<1.0"

COPY server.py /app/server.py
WORKDIR /app
EXPOSE 8080
CMD ["python", "-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8080"]
