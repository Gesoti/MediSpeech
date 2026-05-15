"""Langfuse observability helpers.

All tracing calls are best-effort — a Langfuse outage must never break the API.
"""
from __future__ import annotations

import functools
from typing import TYPE_CHECKING, Any

from app.config import settings
from app.utils.logger import get_logger

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)

try:
    from langfuse import Langfuse

    _langfuse = Langfuse(
        host=settings.langfuse_host,
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
    )
    LANGFUSE_ENABLED = True
    logger.info(f"Langfuse enabled → {settings.langfuse_host}")
except Exception as exc:
    _langfuse = None  # type: ignore[assignment]
    LANGFUSE_ENABLED = False
    logger.warning(f"Langfuse unavailable (tracing disabled): {exc}")


def get_langfuse() -> Any:
    return _langfuse


def create_trace(name: str, **kwargs: Any) -> Any:
    """Create a Langfuse trace. Returns None if Langfuse is disabled."""
    if not LANGFUSE_ENABLED or _langfuse is None:
        return None
    try:
        return _langfuse.trace(name=name, **kwargs)
    except Exception as exc:
        logger.debug(f"Langfuse trace creation failed: {exc}")
        return None


def flush() -> None:
    """Flush pending Langfuse events (call on app shutdown)."""
    if LANGFUSE_ENABLED and _langfuse is not None:
        try:
            _langfuse.flush()
        except Exception:
            pass


def observe(span_name: str | None = None) -> Any:
    """Decorator that wraps an async function in a Langfuse span."""

    def decorator(fn: Any) -> Any:
        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            trace = create_trace(span_name or fn.__name__)
            span = None
            if trace is not None:
                try:
                    span = trace.span(name=span_name or fn.__name__)
                except Exception:
                    pass
            try:
                result = await fn(*args, **kwargs)
                if span is not None:
                    try:
                        span.end()
                    except Exception:
                        pass
                return result
            except Exception as exc:
                if span is not None:
                    try:
                        span.update(level="ERROR", status_message=str(exc))
                        span.end()
                    except Exception:
                        pass
                raise

        return wrapper

    return decorator
