"""Case model."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String, Uuid

from app.db import Base


class Case(Base):
    """Case model for veterinary cases."""

    __tablename__ = "cases"

    id: Column = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Column = Column(Uuid, ForeignKey("users.id"), nullable=False)
    pet_species: Column = Column(String(100), nullable=False)
    pet_breed: Column = Column(String(100), nullable=False)
    study_type: Column = Column(String(100), nullable=False)
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
        return f"<Case {self.id} - {self.pet_species}>"
