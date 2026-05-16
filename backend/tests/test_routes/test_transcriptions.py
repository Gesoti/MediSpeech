"""Tests for /api/transcriptions routes (read and user-edit)."""
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audio import AudioFile
from app.models.transcription import Transcription


async def _seed(test_engine, case_id: UUID) -> dict:
    """Insert audio_file + transcription for the given case; return their IDs."""
    async with AsyncSession(test_engine, expire_on_commit=False) as session:
        audio_file = AudioFile(
            id=uuid4(), case_id=case_id, raw_audio_url="test.wav", duration_seconds=8.0
        )
        session.add(audio_file)
        await session.flush()
        transcription = Transcription(
            id=uuid4(),
            audio_file_id=audio_file.id,
            raw_text="Spleen is mildly enlarged. No free fluid.",
            confidence=0.91,
            model_used="whisper-base",
        )
        session.add(transcription)
        await session.commit()
        return {
            "audio_file_id": audio_file.id,
            "transcription_id": transcription.id,
        }


@pytest.mark.asyncio
async def test_get_transcription_by_audio_file_id(
    client: TestClient, test_engine
) -> None:
    case_id = UUID(
        client.post(
            "/api/cases",
            json={"pet_species": "dog", "pet_breed": "beagle", "study_type": "ultrasound"},
        ).json()["id"]
    )
    ids = await _seed(test_engine, case_id)

    response = client.get(f"/api/transcriptions/{ids['audio_file_id']}")
    assert response.status_code == 200
    data = response.json()
    assert data["raw_text"] == "Spleen is mildly enlarged. No free fluid."
    assert data["confidence"] == 0.91
    assert data["model_used"] == "whisper-base"


def test_get_transcription_not_found(client: TestClient) -> None:
    response = client.get(f"/api/transcriptions/{uuid4()}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_patch_transcription_updates_text(
    client: TestClient, test_engine
) -> None:
    case_id = UUID(
        client.post(
            "/api/cases",
            json={"pet_species": "dog", "pet_breed": "beagle", "study_type": "ultrasound"},
        ).json()["id"]
    )
    ids = await _seed(test_engine, case_id)

    response = client.patch(
        f"/api/transcriptions/{ids['transcription_id']}",
        json={"raw_text": "Corrected: spleen is normal. No free fluid."},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["raw_text"] == "Corrected: spleen is normal. No free fluid."
    assert data["id"] == str(ids["transcription_id"])


@pytest.mark.asyncio
async def test_patch_preserves_other_fields(client: TestClient, test_engine) -> None:
    case_id = UUID(
        client.post(
            "/api/cases",
            json={"pet_species": "cat", "pet_breed": "siamese", "study_type": "CT scan"},
        ).json()["id"]
    )
    ids = await _seed(test_engine, case_id)

    response = client.patch(
        f"/api/transcriptions/{ids['transcription_id']}",
        json={"raw_text": "Revised text only."},
    )
    assert response.status_code == 200
    data = response.json()
    # Confidence and model_used must not be affected by the PATCH
    assert data["confidence"] == 0.91
    assert data["model_used"] == "whisper-base"


def test_patch_transcription_not_found(client: TestClient) -> None:
    response = client.patch(
        f"/api/transcriptions/{uuid4()}",
        json={"raw_text": "Updated text"},
    )
    assert response.status_code == 404
