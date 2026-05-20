"""Report schemas."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ReportCreate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {"transcription_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6"}
        }
    )

    transcription_id: UUID


class ReportResponse(BaseModel):
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
    model_config = ConfigDict(
        strict=True,
        json_schema_extra={
            "example": {
                "clinical_history": "3-year-old Golden Retriever presented with coughing.",
                "findings": "Mild cardiomegaly observed. No pleural effusion.",
                "impressions": "Findings consistent with early-stage dilated cardiomyopathy.",
                "recommendations": "Echocardiogram recommended. Follow-up in 4 weeks.",
                "status": "final",
            }
        },
    )

    clinical_history: str | None = None
    findings: str | None = None
    impressions: str | None = None
    recommendations: str | None = None
    status: str | None = None


class StreamedReportSave(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "clinical_history": "3-year-old Golden Retriever presented with coughing.",
                "findings": "Mild cardiomegaly observed.",
                "impressions": "Consistent with early dilated cardiomyopathy.",
                "recommendations": "Echocardiogram recommended.",
            }
        }
    )

    clinical_history: str | None = None
    findings: str | None = None
    impressions: str | None = None
    recommendations: str | None = None
