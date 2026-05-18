# ---- deps stage ----
# torch (~500 MB) is installed here; this layer is cached unless pyproject.toml/uv.lock changes
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
COPY llm/pyproject.toml llm/uv.lock ./
RUN uv sync --frozen --no-install-project

# ---- runtime stage ----
FROM python:3.12-slim

RUN useradd -m -u 1000 appuser && \
    apt-get update && apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /app/.venv .venv

# shared changes less often than service app code
COPY shared shared
COPY llm/app app

USER appuser

HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD curl -f http://localhost:8002/health || exit 1

CMD ["/app/.venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]
