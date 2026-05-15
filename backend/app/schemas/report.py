"""Report schemas."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ReportCreate(BaseModel):
    """Schema for creating a report."""

    transcription_id: UUID


class ReportResponse(BaseModel):
    """Schema for report response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    case_id: UUID
    transcription_id: UUID
    clinical_history: str | None
    findings: str | None
    impressions: str | None
    recommendations: str | None
    status: str
    created_at: datetime
    updated_at: datetime


class ReportUpdate(BaseModel):
    """Schema for updating a report."""

    model_config = ConfigDict(strict=True)

    clinical_history: str | None = None
    findings: str | None = None
    impressions: str | None = None
    recommendations: str | None = None
    status: str | None = None


class StreamedReportSave(BaseModel):
    """Schema for saving a report produced by the streaming endpoint."""

    clinical_history: str | None = None
    findings: str | None = None
    impressions: str | None = None
    recommendations: str | None = None
