"""Unit tests for AudioService (HTTP client wrapper around transcription microservice)."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _mock_response(data: dict, status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = data
    resp.raise_for_status = MagicMock()
    return resp


@pytest.fixture
def mock_httpx():
    """Patch httpx.AsyncClient so no real HTTP calls are made."""
    with patch("app.services.audio_service.httpx.AsyncClient") as cls:
        client = AsyncMock()
        cls.return_value.__aenter__ = AsyncMock(return_value=client)
        cls.return_value.__aexit__ = AsyncMock(return_value=False)
        yield client


@pytest.mark.asyncio
async def test_transcribe_maps_response_fields(mock_httpx) -> None:
    mock_httpx.post = AsyncMock(
        return_value=_mock_response(
            {"text": "Lame in right foreleg.", "confidence": 0.85, "model": "whisper-base"}
        )
    )
    from app.services.audio_service import AudioService

    result = await AudioService().transcribe(b"audio")
    assert result["text"] == "Lame in right foreleg."
    assert result["confidence"] == 0.85
    assert result["model"] == "whisper-base"


@pytest.mark.asyncio
async def test_transcribe_sends_multipart_file(mock_httpx) -> None:
    mock_httpx.post = AsyncMock(
        return_value=_mock_response({"text": "ok", "confidence": None, "model": "whisper-base"})
    )
    from app.services.audio_service import AudioService

    await AudioService().transcribe(b"bytes", filename="recording.webm")
    call_kwargs = mock_httpx.post.call_args
    assert "files" in call_kwargs.kwargs
    name, content, content_type = call_kwargs.kwargs["files"]["file"]
    assert name == "recording.webm"
    assert content == b"bytes"
    assert content_type == "audio/webm"


@pytest.mark.asyncio
async def test_transcribe_uses_configured_url(mock_httpx) -> None:
    mock_httpx.post = AsyncMock(
        return_value=_mock_response({"text": "x", "confidence": None, "model": "w"})
    )
    from app.config import settings
    from app.services.audio_service import AudioService

    await AudioService().transcribe(b"x")
    url = mock_httpx.post.call_args.args[0]
    assert url == f"{settings.transcription_service_url}/transcribe"


@pytest.mark.asyncio
async def test_transcribe_none_confidence(mock_httpx) -> None:
    mock_httpx.post = AsyncMock(
        return_value=_mock_response({"text": "text", "confidence": None, "model": "whisper-base"})
    )
    from app.services.audio_service import AudioService

    result = await AudioService().transcribe(b"audio")
    assert result["confidence"] is None


@pytest.mark.asyncio
async def test_transcribe_propagates_http_error(mock_httpx) -> None:
    import httpx

    mock_httpx.post = AsyncMock(side_effect=httpx.ConnectError("connection refused"))
    from app.services.audio_service import AudioService

    with pytest.raises(httpx.ConnectError):
        await AudioService().transcribe(b"audio")
