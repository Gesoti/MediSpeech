"""Shared Langfuse tracing — best-effort, never crashes the service."""
from __future__ import annotations

from typing import Any

_lf: Any = None
_init_error: str | None = None
ENABLED: bool = False
_host: str = ""


def init(host: str, public_key: str, secret_key: str) -> None:
    """Call once at service startup to configure Langfuse."""
    global _lf, _init_error, ENABLED, _host
    _host = host
    try:
        from langfuse import Langfuse

        _lf = Langfuse(host=host, public_key=public_key, secret_key=secret_key)
        ENABLED = True
    except Exception as exc:
        _lf = None
        ENABLED = False
        _init_error = str(exc)


def tracing_status() -> dict[str, Any]:
    if not ENABLED:
        return {"enabled": False, "error": _init_error}
    assert _lf is not None
    try:
        _lf.auth_check()
        return {"enabled": True, "host": _host, "connected": True}
    except Exception as exc:
        return {"enabled": True, "host": _host, "connected": False, "error": str(exc)}


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
