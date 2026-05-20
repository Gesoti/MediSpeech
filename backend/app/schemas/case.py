"""Case schemas."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CaseCreate(BaseModel):
    model_config = ConfigDict(
        strict=True,
        json_schema_extra={
            "example": {
                "pet_species": "Canine",
                "pet_breed": "Golden Retriever",
                "study_type": "Thoracic Radiograph",
            }
        },
    )

    pet_species: str = Field(..., min_length=1, max_length=100)
    pet_breed: str = Field(..., min_length=1, max_length=100)
    study_type: str = Field(..., min_length=1, max_length=100)


class CaseUpdate(BaseModel):
    model_config = ConfigDict(
        strict=True,
        json_schema_extra={
            "example": {"study_type": "Abdominal Ultrasound"}
        },
    )

    pet_species: str | None = None
    pet_breed: str | None = None
    study_type: str | None = None


class CaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    pet_species: str
    pet_breed: str
    study_type: str
    created_at: datetime
    updated_at: datetime
