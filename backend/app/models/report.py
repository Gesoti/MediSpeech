"""Report model."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String, Text, Uuid

from app.db import Base


class Report(Base):
    """Report model for clinical reports."""

    __tablename__ = "reports"

    id: Column = Column(Uuid, primary_key=True, default=uuid.uuid4)
    case_id: Column = Column(Uuid, ForeignKey("cases.id"), nullable=False)
    transcription_id: Column = Column(
        Uuid, ForeignKey("transcriptions.id"), nullable=False
    )
    clinical_history: Column = Column(Text, nullable=True)
    findings: Column = Column(Text, nullable=True)
    impressions: Column = Column(Text, nullable=True)
    recommendations: Column = Column(Text, nullable=True)
    status: Column = Column(String(50), default="draft", nullable=False)
    created_at: Column = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Column = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<Report {self.id}>"
