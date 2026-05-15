"""Audio transcription service using OpenAI Whisper."""
import asyncio
import tempfile
from concurrent.futures import ThreadPoolExecutor
from typing import Any, TypedDict

import whisper

from app.utils.logger import get_logger

logger = get_logger(__name__)

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="whisper-worker")


class TranscriptionResult(TypedDict):
    """Result of audio transcription."""

    text: str
    confidence: float | None
    model: str


class AudioService:
    """Service for transcribing audio files using Whisper."""

    def __init__(self) -> None:
        """Lazy-loads Whisper model on first use to avoid blocking startup."""
        self._model: Any = None

    def _get_model(self) -> Any:
        if self._model is None:
            logger.info("Loading Whisper model...")
            self._model = whisper.load_model("base", device="cpu")
            logger.info("Whisper model loaded")
        return self._model

    def _transcribe_sync(self, audio_bytes: bytes) -> TranscriptionResult:
        """CPU-bound transcription — runs in thread pool."""
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=True) as tmp:
            tmp.write(audio_bytes)
            tmp.flush()
            result: dict[str, Any] = self._get_model().transcribe(tmp.name)

        text: str = result.get("text", "")
        logger.info(f"Transcription complete: {len(text)} chars")
        return TranscriptionResult(
            text=text,
            confidence=result.get("confidence"),
            model="whisper-base",
        )

    async def transcribe(self, audio_bytes: bytes) -> TranscriptionResult:
        """Transcribe audio bytes using Whisper (non-blocking)."""
        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(_executor, self._transcribe_sync, audio_bytes)
        except Exception as e:
            logger.error(f"Transcription error: {str(e)}")
            raise


audio_service = AudioService()
