"""Audio file model."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, ForeignKey, String, Uuid

from app.db import Base


class AudioFile(Base):
    """AudioFile model for uploaded audio files."""

    __tablename__ = "audio_files"

    id: Column = Column(Uuid, primary_key=True, default=uuid.uuid4)
    case_id: Column = Column(Uuid, ForeignKey("cases.id"), nullable=False)
    raw_audio_url: Column = Column(String(512), nullable=False)
    duration_seconds: Column = Column(Float, nullable=True)
    created_at: Column = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    def __repr__(self) -> str:
        return f"<AudioFile {self.id}>"

