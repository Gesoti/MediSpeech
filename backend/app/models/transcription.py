"""Transcription model."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, ForeignKey, String, Text, Uuid

from app.db import Base


class Transcription(Base):
    """Transcription model for audio transcriptions."""

    __tablename__ = "transcriptions"

    id: Column = Column(Uuid, primary_key=True, default=uuid.uuid4)
    audio_file_id: Column = Column(
        Uuid, ForeignKey("audio_files.id"), nullable=False
    )
    raw_text: Column = Column(Text, nullable=False)
    confidence: Column = Column(Float, nullable=True)
    model_used: Column = Column(String(100), nullable=False)
    created_at: Column = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    def __repr__(self) -> str:
        return f"<Transcription {self.id}>"
