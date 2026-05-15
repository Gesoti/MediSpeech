"""Audio file upload routes."""
import time
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.audio import AudioFile
from app.models.case import Case
from app.models.transcription import Transcription
from app.services.audio_service import audio_service
from app.utils.logger import get_logger
from app.utils.tracing import create_trace

router = APIRouter(prefix="/api/audio", tags=["audio"])
logger = get_logger(__name__)


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

        audio_file = AudioFile(
            case_id=case_id,
            raw_audio_url=f"uploads/{case_id}/{file.filename}",
            duration_seconds=0.0,
        )
        db.add(audio_file)
        await db.flush()

        logger.info(f"Processing audio: {file.filename}")

        t0 = time.perf_counter()
        transcription_result = await audio_service.transcribe(audio_bytes)
        elapsed = time.perf_counter() - t0

        if trace is not None:
            try:
                trace.generation(
                    name="whisper-transcription",
                    model="whisper-base",
                    input={"audio_bytes": len(audio_bytes)},
                    output=transcription_result["text"],
                    usage={"total_tokens": len(transcription_result["text"].split())},
                    metadata={"elapsed_seconds": round(elapsed, 2)},
                ).end()
            except Exception:
                pass

        transcription = Transcription(
            audio_file_id=audio_file.id,
            raw_text=transcription_result["text"],
            confidence=transcription_result["confidence"],
            model_used=transcription_result["model"],
        )
        db.add(transcription)
        await db.commit()

        if trace is not None:
            try:
                trace.update(output={"transcription_id": str(transcription.id)})
            except Exception:
                pass

        logger.info(f"Audio processed successfully: {audio_file.id}")

        return {
            "audio_file_id": str(audio_file.id),
            "transcription_id": str(transcription.id),
            "text": transcription_result["text"],
            "confidence": transcription_result["confidence"],
        }

    except Exception as e:
        await db.rollback()
        logger.error(f"Audio upload error: {str(e)}")
        raise HTTPException(status_code=500, detail="Audio processing failed")


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
