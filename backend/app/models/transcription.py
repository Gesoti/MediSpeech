"""Transcription model."""
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Transcription(Base):
    """Transcription model for audio transcriptions."""

    __tablename__ = "transcriptions"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    audio_file_id: Mapped[UUID] = mapped_column(ForeignKey("audio_files.id"))
    raw_text: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Float)
    model_used: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    def __repr__(self) -> str:
        return f"<Transcription {self.id}>"
