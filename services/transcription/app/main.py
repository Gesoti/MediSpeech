"""Transcription microservice — Whisper-based audio-to-text."""
from __future__ import annotations

import asyncio
import json
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

import whisper
from fastapi import FastAPI, File, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.config import settings
from app.tracing import create_trace, flush, tracing_status

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
        result: dict[str, Any] = _load_model().transcribe(tmp.name, verbose=False)
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


@app.get("/health/tracing")
async def health_tracing() -> dict[str, Any]:
    return tracing_status()


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

    # avg_logprob from segments is a better confidence proxy than a missing top-level field
    segments: list[dict[str, Any]] = result.get("segments", [])
    confidence: float | None = None
    if segments:
        avg = sum(s.get("avg_logprob", 0.0) for s in segments) / len(segments)
        # Convert log-prob to a 0–1 range: logprob is ≤ 0, clamp at -1 as "low confidence"
        confidence = round(max(0.0, 1.0 + avg), 4)

    return TranscriptionResponse(
        text=text,
        confidence=confidence,
        model=f"whisper-{settings.whisper_model}",
    )


@app.post("/transcribe/stream")
async def transcribe_stream(file: UploadFile = File(...)) -> StreamingResponse:
    """Stream Whisper segments as SSE events.

    Each event carries: {"start": float, "end": float, "text": str}
    A final "data: [DONE]" event signals completion.
    """
    audio_bytes = await file.read()

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(_executor, _transcribe_sync, audio_bytes)

    async def _event_stream() -> AsyncGenerator[str, None]:
        segments: list[dict[str, Any]] = result.get("segments", [])
        if segments:
            for seg in segments:
                payload = json.dumps(
                    {
                        "start": round(seg.get("start", 0.0), 3),
                        "end": round(seg.get("end", 0.0), 3),
                        "text": seg.get("text", "").strip(),
                    }
                )
                yield f"data: {payload}\n\n"
                await asyncio.sleep(0)
        else:
            yield f"data: {json.dumps({'text': result.get('text', '')})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(_event_stream(), media_type="text/event-stream")
