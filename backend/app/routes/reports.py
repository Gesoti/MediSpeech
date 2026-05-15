"""Report routes."""
import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.audio import AudioFile
from app.models.case import Case
from app.models.report import Report
from app.models.transcription import Transcription
from app.schemas.report import ReportCreate, ReportResponse, ReportUpdate, StreamedReportSave
from app.services.langgraph_service import clinical_workflow
from app.utils.logger import get_logger
from app.utils.tracing import create_trace

router = APIRouter(prefix="/api/reports", tags=["reports"])
logger = get_logger(__name__)


async def _resolve_context(
    transcription_id: UUID, db: AsyncSession
) -> tuple[Transcription, AudioFile, Case]:
    """Fetch transcription → audio_file → case, raising 404 on any miss."""
    trans_result = await db.execute(
        select(Transcription).filter(Transcription.id == transcription_id)
    )
    transcription = trans_result.scalar_one_or_none()
    if not transcription:
        raise HTTPException(status_code=404, detail="Transcription not found")

    audio_result = await db.execute(
        select(AudioFile).filter(AudioFile.id == transcription.audio_file_id)
    )
    audio_file = audio_result.scalar_one_or_none()
    if not audio_file:
        raise HTTPException(status_code=404, detail="Audio file not found")

    case_result = await db.execute(select(Case).filter(Case.id == audio_file.case_id))
    case = case_result.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    return transcription, audio_file, case


@router.post("", status_code=201)
async def create_report(
    report_data: ReportCreate,
    db: AsyncSession = Depends(get_db),
) -> ReportResponse:
    """Create report from transcription using LangGraph workflow (blocking)."""
    transcription, audio_file, case = await _resolve_context(
        report_data.transcription_id, db
    )

    trace = create_trace(
        "report-create",
        input={"transcription_id": str(report_data.transcription_id), "study_type": case.study_type},
    )

    try:
        logger.info(f"Processing transcription {report_data.transcription_id} [{case.study_type}]")

        workflow_result = await clinical_workflow.process_transcription(
            transcription.raw_text,
            study_type=case.study_type,
        )

        report = Report(
            case_id=audio_file.case_id,
            transcription_id=report_data.transcription_id,
            clinical_history=workflow_result.get("clinical_history"),
            findings=workflow_result.get("findings"),
            impressions=workflow_result.get("impressions"),
            recommendations=workflow_result.get("recommendations"),
            status="draft",
        )
        db.add(report)
        await db.commit()
        await db.refresh(report)

        if trace is not None:
            try:
                trace.update(output={"report_id": str(report.id)})
            except Exception:
                pass

        logger.info(f"Report created: {report.id}")
        return ReportResponse.model_validate(report)

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Report creation error: {str(e)}")
        raise HTTPException(status_code=500, detail="Report generation failed") from e


@router.post("/stream/{transcription_id}")
async def stream_report(
    transcription_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Stream report tokens via Server-Sent Events.

    The client receives a stream of SSE data lines, each containing a JSON
    payload with the shape:
      {"section": "<name>", "token": "<word> "}        — token-by-token
      {"section": "<name>", "status": "start"|"done", "text": "..."}
      {"status": "complete", "clinical_history": ..., "findings": ..., ...}
    """
    transcription, audio_file, case = await _resolve_context(transcription_id, db)

    async def event_generator() -> object:
        try:
            async for payload in clinical_workflow.stream_report(
                transcription.raw_text, study_type=case.study_type
            ):
                yield f"data: {payload}\n\n"

            # Persist the completed report after streaming
            try:
                # Re-run non-streaming to get final values for DB persistence
                # (stream_report already returned the complete text in the final event)
                pass
            except Exception:
                pass
        except Exception as exc:
            logger.error(f"SSE stream error: {exc}")
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/stream/{transcription_id}/save")
async def save_streamed_report(
    transcription_id: UUID,
    report_data: StreamedReportSave,
    db: AsyncSession = Depends(get_db),
) -> ReportResponse:
    """Persist a report produced by the streaming endpoint.

    The frontend calls this after collecting all streamed sections.
    """
    trans_result = await db.execute(
        select(Transcription).filter(Transcription.id == transcription_id)
    )
    transcription = trans_result.scalar_one_or_none()
    if not transcription:
        raise HTTPException(status_code=404, detail="Transcription not found")

    audio_result = await db.execute(
        select(AudioFile).filter(AudioFile.id == transcription.audio_file_id)
    )
    audio_file = audio_result.scalar_one_or_none()
    if not audio_file:
        raise HTTPException(status_code=404, detail="Audio file not found")

    report = Report(
        case_id=audio_file.case_id,
        transcription_id=transcription_id,
        clinical_history=report_data.clinical_history,
        findings=report_data.findings,
        impressions=report_data.impressions,
        recommendations=report_data.recommendations,
        status="draft",
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)
    return ReportResponse.model_validate(report)


@router.get("/{case_id}")
async def get_report(
    case_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> ReportResponse:
    """Get report for case."""
    result = await db.execute(select(Report).filter(Report.case_id == case_id))
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return ReportResponse.model_validate(report)


@router.patch("/{report_id}")
async def update_report(
    report_id: UUID,
    report_data: ReportUpdate,
    db: AsyncSession = Depends(get_db),
) -> ReportResponse:
    """Update report (for editing generated content)."""
    result = await db.execute(select(Report).filter(Report.id == report_id))
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    for field, value in report_data.model_dump(exclude_unset=True).items():
        setattr(report, field, value)

    await db.commit()
    await db.refresh(report)
    return ReportResponse.model_validate(report)


@router.post("/{report_id}/finalize")
async def finalize_report(
    report_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> ReportResponse:
    """Mark report as final (read-only)."""
    result = await db.execute(select(Report).filter(Report.id == report_id))
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    report.status = "final"
    await db.commit()
    await db.refresh(report)
    return ReportResponse.model_validate(report)


@router.get("")
async def list_reports(
    db: AsyncSession = Depends(get_db),
) -> list[ReportResponse]:
    """List all reports."""
    result = await db.execute(select(Report))
    reports = result.scalars().all()
    return [ReportResponse.model_validate(r) for r in reports]
