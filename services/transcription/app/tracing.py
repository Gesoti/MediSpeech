"""Langfuse tracing — best-effort, never crashes the service."""
from __future__ import annotations

from typing import Any

from app.config import settings

try:
    from langfuse import Langfuse
    _lf = Langfuse(
        host=settings.langfuse_host,
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
    )
    ENABLED = True
except Exception:
    _lf = None  # type: ignore[assignment]
    ENABLED = False


def create_trace(name: str, **kwargs: Any) -> Any:
    if not ENABLED or _lf is None:
        return None
    try:
        return _lf.trace(name=name, **kwargs)
    except Exception:
        return None


def flush() -> None:
    if ENABLED and _lf is not None:
        try:
            _lf.flush()
        except Exception:
            pass
