"""Tests for audio upload and transcription listing routes."""
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audio import AudioFile
from app.models.transcription import Transcription

_FAKE_TRANSCRIPTION = {
    "text": "Patient is a 5-year-old labrador with hip pain.",
    "confidence": 0.92,
    "model": "whisper-base",
}


@pytest.fixture
def mock_transcribe():
    with patch(
        "app.routes.audio.audio_service.transcribe",
        new_callable=AsyncMock,
        return_value=_FAKE_TRANSCRIPTION,
    ) as m:
        yield m


def test_upload_audio_nonexistent_case(client: TestClient) -> None:
    response = client.post(
        f"/api/audio/{uuid4()}/upload",
        files={"file": ("test.webm", b"fake-audio-data", "audio/webm")},
    )
    assert response.status_code == 404


def test_upload_audio_success(client: TestClient, mock_transcribe: AsyncMock) -> None:
    case_resp = client.post(
        "/api/cases",
        json={"pet_species": "dog", "pet_breed": "labrador", "study_type": "x-ray"},
    )
    assert case_resp.status_code == 201
    case_id = case_resp.json()["id"]

    response = client.post(
        f"/api/audio/{case_id}/upload",
        files={"file": ("recording.webm", b"RIFF" + b"\x00" * 44, "audio/webm")},
    )
    assert response.status_code == 200
    data = response.json()
    assert "audio_file_id" in data
    assert "transcription_id" in data
    assert data["text"] == _FAKE_TRANSCRIPTION["text"]
    assert data["confidence"] == _FAKE_TRANSCRIPTION["confidence"]


def test_upload_audio_service_error(client: TestClient) -> None:
    case_resp = client.post(
        "/api/cases",
        json={"pet_species": "cat", "pet_breed": "persian", "study_type": "ultrasound"},
    )
    case_id = case_resp.json()["id"]

    with patch(
        "app.routes.audio.audio_service.transcribe",
        new_callable=AsyncMock,
        side_effect=RuntimeError("Whisper model failed"),
    ):
        response = client.post(
            f"/api/audio/{case_id}/upload",
            files={"file": ("test.webm", b"data", "audio/webm")},
        )
    assert response.status_code == 500
    assert "Audio processing failed" in response.json()["detail"]


def test_list_transcriptions_empty(client: TestClient) -> None:
    case_resp = client.post(
        "/api/cases",
        json={"pet_species": "rabbit", "pet_breed": "dwarf", "study_type": "x-ray"},
    )
    case_id = case_resp.json()["id"]

    response = client.get(f"/api/audio/{case_id}/transcriptions")
    assert response.status_code == 200
    assert response.json() == []


def test_list_transcriptions_after_upload(
    client: TestClient, mock_transcribe: AsyncMock
) -> None:
    case_resp = client.post(
        "/api/cases",
        json={"pet_species": "dog", "pet_breed": "poodle", "study_type": "MRI"},
    )
    case_id = case_resp.json()["id"]

    client.post(
        f"/api/audio/{case_id}/upload",
        files={"file": ("test.webm", b"data", "audio/webm")},
    )

    response = client.get(f"/api/audio/{case_id}/transcriptions")
    assert response.status_code == 200
    items = response.json()
    assert len(items) == 1
    assert items[0]["raw_text"] == _FAKE_TRANSCRIPTION["text"]


@pytest.mark.asyncio
async def test_get_transcription_by_id(client: TestClient, test_engine) -> None:
    case_resp = client.post(
        "/api/cases",
        json={"pet_species": "cat", "pet_breed": "maine coon", "study_type": "CT scan"},
    )
    case_id = UUID(case_resp.json()["id"])

    async with AsyncSession(test_engine, expire_on_commit=False) as session:
        audio_file = AudioFile(
            id=uuid4(), case_id=case_id, raw_audio_url="test.wav", duration_seconds=5.0
        )
        session.add(audio_file)
        await session.flush()
        transcription = Transcription(
            id=uuid4(),
            audio_file_id=audio_file.id,
            raw_text="Herniated disc at L4-L5.",
            confidence=0.88,
            model_used="whisper-base",
        )
        session.add(transcription)
        await session.commit()
        transcription_id = transcription.id

    response = client.get(f"/api/audio/{transcription_id}")
    assert response.status_code == 200
    assert response.json()["raw_text"] == "Herniated disc at L4-L5."


def test_get_transcription_not_found(client: TestClient) -> None:
    response = client.get(f"/api/audio/{uuid4()}")
    assert response.status_code == 404
