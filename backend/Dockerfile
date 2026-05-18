# ---- deps stage ----
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

# ---- runtime stage ----
FROM python:3.12-slim

RUN useradd -m -u 1000 appuser && \
    apt-get update && apt-get install -y --no-install-recommends \
        curl ffmpeg postgresql-client \
    && rm -rf /var/lib/apt/lists/* && \
    mkdir /audio && chown appuser:appuser /audio

WORKDIR /app

COPY --from=builder /app/.venv .venv

# alembic config changes less often than app source
COPY alembic.ini alembic.ini
COPY alembic alembic
COPY --chown=appuser:appuser app app

USER appuser

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["/app/.venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
