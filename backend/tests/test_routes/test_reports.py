"""Tests for report routes and LangGraph integration."""
import pytest
from uuid import UUID, uuid4
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audio import AudioFile
from app.models.report import Report
from app.models.transcription import Transcription


@pytest.mark.asyncio
async def test_create_report(client, test_engine):
    """Test report creation from transcription using LangGraph workflow."""
    response = client.post(
        "/api/cases",
        json={"pet_species": "dog", "pet_breed": "labrador", "study_type": "x-ray"},
    )
    assert response.status_code == 201
    case_id = UUID(response.json()["id"])

    async with AsyncSession(test_engine, expire_on_commit=False) as session:
        audio_file = AudioFile(
            id=uuid4(), case_id=case_id, raw_audio_url="test.wav", duration_seconds=10.0
        )
        session.add(audio_file)
        await session.flush()

        transcription = Transcription(
            id=uuid4(),
            audio_file_id=audio_file.id,
            raw_text="Dog shows signs of arthritis. Left hip dysplasia evident.",
            confidence=0.95,
            model_used="whisper",
        )
        session.add(transcription)
        await session.commit()
        # Capture IDs before session closes — instance is detached after the block
        transcription_id = transcription.id

    response = client.post(
        "/api/reports",
        json={"transcription_id": str(transcription_id)},
    )

    # LLM model won't be available in CI — skip rather than fail
    if response.status_code == 500 and "Report generation failed" in response.json().get(
        "detail", ""
    ):
        pytest.skip("LLM model not available in test environment")

    assert response.status_code == 201
    report = response.json()
    assert "id" in report
    assert report["case_id"] == str(case_id)
    assert report["transcription_id"] == str(transcription_id)
    assert report["status"] == "draft"


@pytest.mark.asyncio
async def test_get_report(client):
    """Test getting a report for a case — returns 404 when no report exists."""
    response = client.post(
        "/api/cases",
        json={"pet_species": "dog", "pet_breed": "labrador", "study_type": "x-ray"},
    )
    assert response.status_code == 201
    case_id = response.json()["id"]

    response = client.get(f"/api/reports/{case_id}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_reports(client):
    """Test listing all reports."""
    response = client.get("/api/reports")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_update_report(client, test_engine):
    """Test updating a report."""
    response = client.post(
        "/api/cases",
        json={"pet_species": "dog", "pet_breed": "labrador", "study_type": "x-ray"},
    )
    assert response.status_code == 201
    case_id = UUID(response.json()["id"])

    async with AsyncSession(test_engine, expire_on_commit=False) as session:
        audio_file = AudioFile(
            id=uuid4(), case_id=case_id, raw_audio_url="test.wav", duration_seconds=10.0
        )
        session.add(audio_file)
        await session.flush()

        transcription = Transcription(
            id=uuid4(),
            audio_file_id=audio_file.id,
            raw_text="Test transcription",
            confidence=0.95,
            model_used="whisper",
        )
        session.add(transcription)
        await session.flush()

        report = Report(
            id=uuid4(),
            case_id=case_id,
            transcription_id=transcription.id,
            clinical_history="Test history",
            findings="Test findings",
            impressions="Test impressions",
            recommendations="Test recommendations",
            status="draft",
        )
        session.add(report)
        await session.commit()
        report_id = report.id

    response = client.patch(
        f"/api/reports/{report_id}",
        json={"findings": "Updated findings", "status": "draft"},
    )
    assert response.status_code == 200
    assert response.json()["findings"] == "Updated findings"


@pytest.mark.asyncio
async def test_finalize_report(client, test_engine):
    """Test finalizing a report."""
    response = client.post(
        "/api/cases",
        json={"pet_species": "dog", "pet_breed": "labrador", "study_type": "x-ray"},
    )
    assert response.status_code == 201
    case_id = UUID(response.json()["id"])

    async with AsyncSession(test_engine, expire_on_commit=False) as session:
        audio_file = AudioFile(
            id=uuid4(), case_id=case_id, raw_audio_url="test.wav", duration_seconds=10.0
        )
        session.add(audio_file)
        await session.flush()

        transcription = Transcription(
            id=uuid4(),
            audio_file_id=audio_file.id,
            raw_text="Test transcription",
            confidence=0.95,
            model_used="whisper",
        )
        session.add(transcription)
        await session.flush()

        report = Report(
            id=uuid4(),
            case_id=case_id,
            transcription_id=transcription.id,
            clinical_history="Test history",
            findings="Test findings",
            impressions="Test impressions",
            recommendations="Test recommendations",
            status="draft",
        )
        session.add(report)
        await session.commit()
        report_id = report.id

    response = client.post(f"/api/reports/{report_id}/finalize")
    assert response.status_code == 200
    assert response.json()["status"] == "final"
