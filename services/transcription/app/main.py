"""Transcription microservice — faster-whisper with true VAD-based streaming."""
from __future__ import annotations

import asyncio
import json
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from faster_whisper import WhisperModel
from faster_whisper.transcribe import Segment
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.config import settings
from app.tracing import create_trace, flush, init, tracing_status

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="whisper")
_model: WhisperModel | None = None

_VAD_PARAMS: dict[str, int] = {"min_silence_duration_ms": 500}


def _validate_audio(data: bytes) -> None:
    """Reject files that don't match known audio magic bytes before hitting ffmpeg."""
    header = data[:12]
    if (
        header[:4] == b"\x1a\x45\xdf\xa3"  # WebM / MKV
        or header[:4] == b"RIFF"  # WAV
        or header[:3] == b"ID3"  # MP3 with ID3 tag
        or header[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2")  # raw MP3 frames
        or header[:4] == b"OggS"  # OGG
        or header[4:8] == b"ftyp"  # M4A / AAC / MP4 container
    ):
        return
    raise HTTPException(
        status_code=422,
        detail="Unsupported audio format. Accepted: webm, wav, mp3, ogg, m4a",
    )


def _load_model() -> WhisperModel:
    global _model
    if _model is None:
        # int8 quantisation halves memory with negligible quality loss on CPU
        _model = WhisperModel(
            settings.whisper_model,
            device="cpu",
            compute_type="int8",
            # only needed for gated/private HF repos; None is fine for public models
            use_auth_token=settings.hf_token,
        )
    return _model


def _transcribe_sync(audio_bytes: bytes) -> tuple[list[Segment], float | None]:
    """Blocking full transcription. Returns (segments, confidence)."""
    model = _load_model()
    with tempfile.NamedTemporaryFile(suffix=".webm", delete=True) as tmp:
        tmp.write(audio_bytes)
        tmp.flush()
        segments_gen, _info = model.transcribe(
            tmp.name,
            vad_filter=True,
            vad_parameters=_VAD_PARAMS,
        )
        segments = list(segments_gen)

    confidence: float | None = None
    if segments:
        avg = sum(s.avg_logprob for s in segments) / len(segments)
        # Convert log-prob to 0–1: logprob ≤ 0, clamp at -1 as "low confidence"
        confidence = round(max(0.0, 1.0 + avg), 4)

    return segments, confidence


def _stream_segments_worker(
    audio_bytes: bytes,
    out_queue: asyncio.Queue[Segment | None],
    loop: asyncio.AbstractEventLoop,
) -> None:
    """Thread-pool worker: iterates the faster-whisper lazy generator and pushes
    each Segment onto the asyncio queue as it's decoded, then pushes None sentinel."""
    model = _load_model()
    with tempfile.NamedTemporaryFile(suffix=".webm", delete=True) as tmp:
        tmp.write(audio_bytes)
        tmp.flush()
        segments_gen, _info = model.transcribe(
            tmp.name,
            vad_filter=True,
            vad_parameters=_VAD_PARAMS,
        )
        for seg in segments_gen:
            loop.call_soon_threadsafe(out_queue.put_nowait, seg)
    loop.call_soon_threadsafe(out_queue.put_nowait, None)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    init(settings.langfuse_host, settings.langfuse_public_key, settings.langfuse_secret_key)
    loop = asyncio.get_running_loop()
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
async def health_tracing() -> dict[str, object]:
    return tracing_status()


@app.post("/transcribe", response_model=TranscriptionResponse)
async def transcribe(file: UploadFile = File(...)) -> TranscriptionResponse:
    audio_bytes = await file.read()
    _validate_audio(audio_bytes)

    trace = create_trace("transcription", input={"filename": file.filename, "bytes": len(audio_bytes)})
    t0 = time.perf_counter()

    loop = asyncio.get_running_loop()
    segments, confidence = await loop.run_in_executor(_executor, _transcribe_sync, audio_bytes)

    elapsed = time.perf_counter() - t0
    text = " ".join(s.text.strip() for s in segments)

    if trace is not None:
        try:
            trace.generation(
                name="whisper",
                model=f"faster-whisper-{settings.whisper_model}",
                output=text,
                usage={"total_tokens": len(text.split())},
                metadata={"elapsed_seconds": round(elapsed, 2)},
            ).end()
            trace.update(output={"text_length": len(text)})
        except Exception:
            pass

    return TranscriptionResponse(
        text=text,
        confidence=confidence,
        model=f"faster-whisper-{settings.whisper_model}",
    )


@app.post("/transcribe/stream")
async def transcribe_stream(file: UploadFile = File(...)) -> StreamingResponse:
    """True streaming: yields SSE segment events as faster-whisper decodes them.

    Each event: {"start": float, "end": float, "text": str}
    Final event: [DONE]
    """
    audio_bytes = await file.read()
    _validate_audio(audio_bytes)

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[Segment | None] = asyncio.Queue()

    # Kick off decoding in thread pool — segments arrive on queue as decoded
    loop.run_in_executor(_executor, _stream_segments_worker, audio_bytes, queue, loop)

    async def _event_stream() -> AsyncGenerator[str, None]:
        collected: list[Segment] = []
        while True:
            seg = await queue.get()
            if seg is None:
                break
            collected.append(seg)
            payload = json.dumps(
                {
                    "start": round(seg.start, 3),
                    "end": round(seg.end, 3),
                    "text": seg.text.strip(),
                }
            )
            yield f"data: {payload}\n\n"

        # Emit metadata so the backend can persist confidence + model without
        # a separate blocking call
        confidence: float | None = None
        if collected:
            avg = sum(s.avg_logprob for s in collected) / len(collected)
            confidence = round(max(0.0, 1.0 + avg), 4)
        yield f"data: {json.dumps({'type': 'meta', 'model': f'faster-whisper-{settings.whisper_model}', 'confidence': confidence})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(_event_stream(), media_type="text/event-stream")
