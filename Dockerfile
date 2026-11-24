FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy project definition and install dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir .

# Copy application source code
COPY . .

# Install package in editable/local mode
RUN pip install --no-cache-dir -e .

# Expose default HTTP/SSE port
EXPOSE 8000

# Environment variables defaults
ENV PORT=8000
ENV MCP_TRANSPORT=sse

# Healthcheck for Railway / Docker
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Entrypoint running multi-transport FastMCP server
CMD ["sh", "-c", "python -m omnijob_mcp --transport ${MCP_TRANSPORT:-sse} --port ${PORT:-8000} --host 0.0.0.0"]
