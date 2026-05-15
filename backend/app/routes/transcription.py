"""Transcription routes."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.transcription import Transcription
from app.schemas.transcription import TranscriptionResponse
from app.utils.logger import get_logger

router = APIRouter(prefix="/api/transcriptions", tags=["transcriptions"])
logger = get_logger(__name__)


class TranscriptionUpdate(BaseModel):
    raw_text: str


@router.get("/{audio_file_id}")
async def get_transcription(
    audio_file_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> TranscriptionResponse:
    """Get transcription for audio file."""
    result = await db.execute(
        select(Transcription).filter(Transcription.audio_file_id == audio_file_id)
    )
    transcription = result.scalar_one_or_none()
    if not transcription:
        raise HTTPException(status_code=404, detail="Transcription not found")
    return TranscriptionResponse.model_validate(transcription)


@router.patch("/{transcription_id}")
async def update_transcription(
    transcription_id: UUID,
    body: TranscriptionUpdate,
    db: AsyncSession = Depends(get_db),
) -> TranscriptionResponse:
    """Update transcription text (user correction)."""
    result = await db.execute(
        select(Transcription).filter(Transcription.id == transcription_id)
    )
    transcription = result.scalar_one_or_none()
    if not transcription:
        raise HTTPException(status_code=404, detail="Transcription not found")

    transcription.raw_text = body.raw_text
    await db.commit()
    await db.refresh(transcription)
    return TranscriptionResponse.model_validate(transcription)
