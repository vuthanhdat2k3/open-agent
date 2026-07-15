FROM python:3.11-slim

WORKDIR /app

# Install dependencies first for better layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code.
COPY server.py auth.py ./

# Run as a non-root user.
RUN useradd --create-home --uid 1000 mcpuser \
    && chown -R mcpuser:mcpuser /app
USER mcpuser

# SSE mode by default: open-agent connects via transport="sse", url="http://host:8001/sse".
# Secrets (credentials.json / token.json) are mounted at runtime, NOT baked into the image.
ENV MCP_TRANSPORT=sse \
    MCP_HOST=0.0.0.0 \
    MCP_PORT=8001 \
    GOOGLE_CREDENTIALS_PATH=/app/credentials.json \
    GOOGLE_TOKEN_PATH=/app/token.json

EXPOSE 8001

ENTRYPOINT ["python", "server.py"]
