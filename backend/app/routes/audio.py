"""Audio file upload routes."""
import asyncio
import contextlib
import json
import os
import pathlib
import re
import time
from collections.abc import AsyncGenerator
from typing import Any
from uuid import UUID

import websockets
import websockets.exceptions
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_db
from app.models.audio import AudioFile
from app.models.case import Case
from app.models.transcription import Transcription
from app.services.audio_service import audio_service
from app.utils.logger import get_logger
from app.utils.tracing import create_trace

router = APIRouter(prefix="/api/audio", tags=["audio"])
logger = get_logger(__name__)

_SAFE_NAME_RE = re.compile(r"[^\w\-.]")


def _safe_filename(name: str | None, fallback: str = "audio.webm") -> str:
    """Return a filename with no path components and only safe characters."""
    stem = pathlib.Path(name or fallback).name
    return _SAFE_NAME_RE.sub("_", stem) or fallback


@router.post("/{case_id}/upload")
async def upload_audio(
    case_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Upload audio file and transcribe it."""
    # Verify case exists
    case_result = await db.execute(
        select(Case).filter(Case.id == case_id)
    )
    case = case_result.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    trace = create_trace(
        "transcription",
        input={"case_id": str(case_id), "filename": file.filename, "content_type": file.content_type},
    )

    try:
        audio_bytes = await file.read()

        # Persist audio bytes to the mounted volume so they survive restarts
        audio_dir = os.path.join(settings.audio_storage_path, str(case_id))
        os.makedirs(audio_dir, exist_ok=True)
        filename = _safe_filename(file.filename)
        audio_path = os.path.join(audio_dir, filename)
        with open(audio_path, "wb") as fh:
            fh.write(audio_bytes)

        audio_file = AudioFile(
            case_id=case_id,
            raw_audio_url=f"{case_id}/{filename}",
            duration_seconds=0.0,
        )
        db.add(audio_file)
        await db.flush()

        logger.info(f"Processing audio: {file.filename}")

        t0 = time.perf_counter()
        transcription_result = await audio_service.transcribe(
            audio_bytes, filename=_safe_filename(file.filename)
        )
        elapsed = time.perf_counter() - t0

        if trace is not None:
            with contextlib.suppress(Exception):
                trace.generation(
                    name="whisper-transcription",
                    model="whisper-base",
                    input={"audio_bytes": len(audio_bytes)},
                    output=transcription_result["text"],
                    usage={"total_tokens": len(transcription_result["text"].split())},
                    metadata={"elapsed_seconds": round(elapsed, 2)},
                ).end()

        transcription = Transcription(
            audio_file_id=audio_file.id,
            raw_text=transcription_result["text"],
            confidence=transcription_result["confidence"],
            model_used=transcription_result["model"],
        )
        db.add(transcription)
        await db.commit()

        if trace is not None:
            with contextlib.suppress(Exception):
                trace.update(output={"transcription_id": str(transcription.id)})

        logger.info(f"Audio processed successfully: {audio_file.id}")

        return {
            "transcription_id": str(transcription.id),
            "audio_file_id": str(audio_file.id),
            "text": transcription_result["text"],
            "confidence": transcription_result["confidence"],
            "model_used": transcription_result["model"],
            "created_at": transcription.created_at.isoformat(),
        }

    except Exception as e:
        await db.rollback()
        logger.error(f"Audio upload error: {str(e)}")
        raise HTTPException(status_code=500, detail="Audio processing failed") from None


@router.post("/{case_id}/upload/stream")
async def upload_audio_stream(
    case_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Upload audio and stream transcription segments as SSE.

    Events emitted:
      {"type": "segment", "start": float, "end": float, "text": str}
      {"type": "done", "transcription_id": str, "audio_file_id": str,
       "confidence": float | null, "model": str, "raw_text": str}
      {"type": "error", "detail": str}
    """
    case_result = await db.execute(select(Case).filter(Case.id == case_id))
    if not case_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Case not found")

    audio_bytes = await file.read()

    # Persist audio file to the mounted volume
    audio_dir = os.path.join(settings.audio_storage_path, str(case_id))
    os.makedirs(audio_dir, exist_ok=True)
    filename = _safe_filename(file.filename)
    with open(os.path.join(audio_dir, filename), "wb") as fh:
        fh.write(audio_bytes)

    audio_file = AudioFile(
        case_id=case_id,
        raw_audio_url=f"{case_id}/{filename}",
        duration_seconds=0.0,
    )
    db.add(audio_file)
    await db.flush()
    audio_file_id = audio_file.id

    async def event_stream() -> AsyncGenerator[str, None]:
        segments: list[dict[str, Any]] = []
        meta: dict[str, Any] = {"model": "faster-whisper", "confidence": None}
        try:
            async for event in audio_service.transcribe_stream(audio_bytes, filename):
                if event.get("type") == "meta":
                    meta = event
                else:
                    segments.append(event)
                    yield f"data: {json.dumps({'type': 'segment', 'start': event['start'], 'end': event['end'], 'text': event['text']})}\n\n"
        except Exception as e:
            await db.rollback()
            logger.error(f"Stream transcription error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'detail': 'Transcription failed'})}\n\n"
            return

        raw_text = " ".join(s["text"] for s in segments)
        transcription = Transcription(
            audio_file_id=audio_file_id,
            raw_text=raw_text,
            confidence=meta.get("confidence"),
            model_used=meta.get("model", "faster-whisper"),
        )
        db.add(transcription)
        await db.commit()

        yield f"data: {json.dumps({'type': 'done', 'transcription_id': str(transcription.id), 'audio_file_id': str(audio_file_id), 'confidence': meta.get('confidence'), 'model': meta.get('model', 'faster-whisper'), 'raw_text': raw_text})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/preview")
async def preview_transcribe(
    file: UploadFile = File(...),
) -> dict[str, str]:
    """Transcribe a short audio chunk for live preview — no DB writes."""
    audio_bytes = await file.read()
    try:
        result = await audio_service.transcribe(audio_bytes, filename=file.filename or "chunk.webm")
        return {"text": result["text"]}
    except Exception as e:
        logger.warning(f"Preview transcription failed: {e}")
        return {"text": ""}


@router.get("/{case_id}/transcriptions")
async def list_transcriptions(
    case_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """Get all transcriptions for a case."""
    result = await db.execute(
        select(Transcription)
        .join(AudioFile)
        .filter(AudioFile.case_id == case_id)
    )
    transcriptions = result.scalars().all()
    return [
        {
            "id": str(t.id),
            "audio_file_id": str(t.audio_file_id),
            "raw_text": t.raw_text,
            "confidence": t.confidence,
            "model_used": t.model_used,
            "created_at": t.created_at.isoformat(),
        }
        for t in transcriptions
    ]


@router.get("/{transcription_id}")
async def get_transcription(
    transcription_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get a specific transcription."""
    result = await db.execute(
        select(Transcription).filter(Transcription.id == transcription_id)
    )
    transcription = result.scalar_one_or_none()
    if not transcription:
        raise HTTPException(status_code=404, detail="Transcription not found")

    return {
        "id": str(transcription.id),
        "audio_file_id": str(transcription.audio_file_id),
        "raw_text": transcription.raw_text,
        "confidence": transcription.confidence,
        "model_used": transcription.model_used,
        "created_at": transcription.created_at.isoformat(),
    }


@router.websocket("/{case_id}/ws")
async def audio_ws(
    websocket: WebSocket,
    case_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Live recording WebSocket proxy.

    Streams binary audio chunks from the browser to the transcription service,
    forwards partial text back in real-time, and persists the final transcription
    to the database when the session ends.
    """
    case_result = await db.execute(select(Case).filter(Case.id == case_id))
    if not case_result.scalar_one_or_none():
        await websocket.close(code=4004, reason="Case not found")
        return

    await websocket.accept()

    audio_buffer = bytearray()

    try:
        ts_ws_url = settings.transcription_service_url.replace("http://", "ws://").replace("https://", "wss://") + "/ws/transcribe"
        async with websockets.connect(ts_ws_url) as ts_ws:

            async def _forward_to_ts() -> None:
                """Relay browser chunks → transcription service."""
                try:
                    while True:
                        msg = await websocket.receive()
                        if msg.get("bytes") is not None:
                            chunk: bytes = msg["bytes"]
                            audio_buffer.extend(chunk)
                            await ts_ws.send(chunk)
                        elif msg.get("text") is not None:
                            # Pass control messages ({"type":"end"}) straight through
                            await ts_ws.send(msg["text"])
                            if json.loads(msg["text"]).get("type") == "end":
                                return
                        elif msg.get("type") == "websocket.disconnect":
                            return
                except WebSocketDisconnect:
                    pass

            async def _forward_to_browser() -> None:
                """Relay transcription service messages → browser, persisting on final."""
                async for raw in ts_ws:
                    event: dict[str, Any] = json.loads(raw)

                    if event.get("type") == "final":
                        # Persist audio + transcription to DB
                        audio_dir = os.path.join(settings.audio_storage_path, str(case_id))
                        os.makedirs(audio_dir, exist_ok=True)
                        filename = f"recording_{int(time.time())}.webm"
                        with open(os.path.join(audio_dir, filename), "wb") as fh:
                            fh.write(bytes(audio_buffer))

                        audio_file = AudioFile(
                            case_id=case_id,
                            raw_audio_url=f"{case_id}/{filename}",
                            duration_seconds=0.0,
                        )
                        db.add(audio_file)
                        await db.flush()

                        transcription = Transcription(
                            audio_file_id=audio_file.id,
                            raw_text=event.get("text", ""),
                            confidence=event.get("confidence"),
                            model_used=event.get("model", "faster-whisper"),
                        )
                        db.add(transcription)
                        await db.commit()

                        enriched = {
                            **event,
                            "transcription_id": str(transcription.id),
                            "audio_file_id": str(audio_file.id),
                        }
                        with contextlib.suppress(Exception):
                            await websocket.send_text(json.dumps(enriched))
                        return

                    with contextlib.suppress(Exception):
                        await websocket.send_text(raw)

            await asyncio.gather(_forward_to_ts(), _forward_to_browser())

    except websockets.exceptions.WebSocketException as exc:
        logger.error(f"Transcription service WS error: {exc}")
        with contextlib.suppress(Exception):
            await websocket.send_text(
                json.dumps({"type": "error", "detail": "Transcription service unavailable"})
            )
    finally:
        with contextlib.suppress(Exception):
            await websocket.close()
