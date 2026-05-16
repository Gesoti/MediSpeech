"""Transcription microservice — Whisper-based audio-to-text."""
from __future__ import annotations

import asyncio
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

import whisper
from fastapi import FastAPI, File, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.config import settings
from app.tracing import create_trace, flush

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="whisper")
_model: Any = None


def _load_model() -> Any:
    global _model
    if _model is None:
        _model = whisper.load_model(settings.whisper_model, device="cpu")
    return _model


def _transcribe_sync(audio_bytes: bytes) -> dict[str, Any]:
    with tempfile.NamedTemporaryFile(suffix=".webm", delete=True) as tmp:
        tmp.write(audio_bytes)
        tmp.flush()
        result: dict[str, Any] = _load_model().transcribe(tmp.name)
    return result


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(_executor, _load_model)
    yield
    flush()


app = FastAPI(title="MediSpeech Transcription Service", lifespan=lifespan)


class TranscriptionResponse(BaseModel):
    text: str
    confidence: float | None
    model: str


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy", "service": "transcription"}


@app.post("/transcribe", response_model=TranscriptionResponse)
async def transcribe(file: UploadFile = File(...)) -> TranscriptionResponse:
    audio_bytes = await file.read()

    trace = create_trace("transcription", input={"filename": file.filename, "bytes": len(audio_bytes)})
    t0 = time.perf_counter()

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(_executor, _transcribe_sync, audio_bytes)

    elapsed = time.perf_counter() - t0
    text: str = result.get("text", "")

    if trace is not None:
        try:
            trace.generation(
                name="whisper",
                model=f"whisper-{settings.whisper_model}",
                output=text,
                usage={"total_tokens": len(text.split())},
                metadata={"elapsed_seconds": round(elapsed, 2)},
            ).end()
            trace.update(output={"text_length": len(text)})
        except Exception:
            pass

    return TranscriptionResponse(
        text=text,
        confidence=result.get("confidence"),
        model=f"whisper-{settings.whisper_model}",
    )
