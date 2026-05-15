"""Case schemas."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CaseCreate(BaseModel):
    """Schema for creating a case."""

    model_config = ConfigDict(strict=True)

    pet_species: str = Field(..., min_length=1, max_length=100)
    pet_breed: str = Field(..., min_length=1, max_length=100)
    study_type: str = Field(..., min_length=1, max_length=100)


class CaseUpdate(BaseModel):
    """Schema for updating a case."""

    model_config = ConfigDict(strict=True)

    pet_species: str | None = None
    pet_breed: str | None = None
    study_type: str | None = None


class CaseResponse(BaseModel):
    """Schema for case response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    pet_species: str
    pet_breed: str
    study_type: str
    created_at: datetime
    updated_at: datetime
