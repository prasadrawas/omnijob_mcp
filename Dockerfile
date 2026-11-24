# Production Dockerfile for OmniJob MCP (Railway & Cloud Deployment)
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (curl for healthcheck, git)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first for optimal Docker layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy source repository into /app/omnijob_mcp
COPY . /app/omnijob_mcp/

# Set environment variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV PORT=8000
ENV MCP_TRANSPORT=sse

# Expose standard port for SSE mode (Railway dynamically maps $PORT)
EXPOSE 8000

# Health check probe against /health
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/health || exit 1

# Default command: run in SSE mode respecting Railway's dynamic $PORT and 0.0.0.0 host
CMD ["sh", "-c", "python -m omnijob_mcp --transport ${MCP_TRANSPORT:-sse} --port ${PORT:-8000} --host 0.0.0.0"]
