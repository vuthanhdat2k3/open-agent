FROM python:3.11-slim

WORKDIR /app
COPY pyproject.toml server.py ./
RUN pip install --no-cache-dir .

RUN useradd --create-home --uid 1000 cimcp \
    && chown -R cimcp:cimcp /app
USER cimcp

ENV MCP_TRANSPORT=sse \
    MCP_HOST=0.0.0.0 \
    MCP_PORT=8301
EXPOSE 8301
ENTRYPOINT ["python", "server.py"]
