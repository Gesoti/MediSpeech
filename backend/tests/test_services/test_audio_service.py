"""Unit tests for AudioService (Whisper transcription wrapper)."""
from unittest.mock import MagicMock, patch

import pytest


def _make_service(whisper_result: dict) -> object:
    """Return an AudioService with a pre-loaded fake Whisper model."""
    from app.services.audio_service import AudioService

    fake_model = MagicMock()
    fake_model.transcribe.return_value = whisper_result
    service = AudioService()
    service._model = fake_model
    return service


def test_transcribe_sync_maps_fields() -> None:
    service = _make_service({"text": "Lame in right foreleg.", "confidence": 0.85})
    result = service._transcribe_sync(b"fake-audio")  # type: ignore[attr-defined]
    assert result["text"] == "Lame in right foreleg."
    assert result["confidence"] == 0.85
    assert result["model"] == "whisper-base"


def test_transcribe_sync_none_confidence() -> None:
    """Confidence may be None when Whisper does not return it."""
    service = _make_service({"text": "No confidence value.", "confidence": None})
    result = service._transcribe_sync(b"audio")  # type: ignore[attr-defined]
    assert result["confidence"] is None
    assert result["text"] == "No confidence value."


def test_transcribe_sync_empty_text() -> None:
    service = _make_service({"text": "", "confidence": 0.0})
    result = service._transcribe_sync(b"silence")  # type: ignore[attr-defined]
    assert result["text"] == ""


@pytest.mark.asyncio
async def test_transcribe_async_returns_result() -> None:
    service = _make_service({"text": "Hip dysplasia.", "confidence": 0.9})
    result = await service.transcribe(b"audio-data")  # type: ignore[attr-defined]
    assert result["text"] == "Hip dysplasia."
    assert result["model"] == "whisper-base"


def test_model_lazy_loads_once() -> None:
    """_get_model calls whisper.load_model exactly once and reuses the result."""
    with patch("whisper.load_model") as mock_load:
        mock_load.return_value = MagicMock()
        from app.services.audio_service import AudioService

        service = AudioService()
        assert service._model is None

        m1 = service._get_model()
        m2 = service._get_model()

        assert m1 is m2
        mock_load.assert_called_once_with("base", device="cpu")


@pytest.mark.asyncio
async def test_transcribe_propagates_exceptions() -> None:
    from app.services.audio_service import AudioService

    fake_model = MagicMock()
    fake_model.transcribe.side_effect = RuntimeError("out of memory")
    service = AudioService()
    service._model = fake_model

    with pytest.raises(RuntimeError, match="out of memory"):
        await service.transcribe(b"audio")
