"""Audio schemas."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AudioFileResponse(BaseModel):
    """Schema for audio file response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    case_id: UUID
    raw_audio_url: str
    duration_seconds: float | None
    created_at: datetime
