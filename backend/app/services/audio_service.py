"""Audio transcription service — delegates to the transcription microservice."""
from collections.abc import AsyncGenerator
from typing import Any, TypedDict
import json

import httpx

from app.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


class TranscriptionResult(TypedDict):
    text: str
    confidence: float | None
    model: str


class AudioService:
    """Calls the standalone transcription microservice over HTTP."""

    async def transcribe(
        self, audio_bytes: bytes, filename: str = "audio.webm"
    ) -> TranscriptionResult:
        logger.info(f"Sending {len(audio_bytes)} bytes to transcription service")
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{settings.transcription_service_url}/transcribe",
                files={"file": (filename, audio_bytes, "audio/webm")},
            )
            response.raise_for_status()
        data = response.json()
        logger.info("Transcription received from service")
        return TranscriptionResult(
            text=data["text"],
            confidence=data.get("confidence"),
            model=data["model"],
        )

    async def transcribe_stream(
        self, audio_bytes: bytes, filename: str = "audio.webm"
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Proxy the transcription service SSE stream.

        Yields each parsed event dict (segment or meta); stops before [DONE].
        """
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                f"{settings.transcription_service_url}/transcribe/stream",
                files={"file": (filename, audio_bytes, "audio/webm")},
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[6:]
                    if data == "[DONE]":
                        return
                    yield json.loads(data)


audio_service = AudioService()
