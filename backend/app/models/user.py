"""User model."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, String, Uuid

from app.db import Base


class User(Base):
    """User model."""

    __tablename__ = "users"

    id: Column = Column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Column = Column(String(255), unique=True, nullable=False, index=True)
    name: Column = Column(String(255), nullable=False)
    created_at: Column = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    def __repr__(self) -> str:
        return f"<User {self.email}>"
