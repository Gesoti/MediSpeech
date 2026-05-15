"""Transcription schemas."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class TranscriptionResponse(BaseModel):
    """Schema for transcription response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    audio_file_id: UUID
    raw_text: str
    confidence: float | None
    model_used: str
    created_at: datetime
