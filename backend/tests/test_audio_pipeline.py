"""Tests for audio pipeline (case CRUD via SQLite in-memory DB)."""
import pytest
from fastapi.testclient import TestClient


def test_health_check(client: TestClient) -> None:
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "medispeech-api"


def test_create_case(client: TestClient) -> None:
    """Test case creation."""
    response = client.post(
        "/api/cases",
        json={
            "pet_species": "dog",
            "pet_breed": "labrador",
            "study_type": "x-ray",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["pet_species"] == "dog"
    assert data["pet_breed"] == "labrador"
    assert data["study_type"] == "x-ray"
    assert "id" in data
    assert "user_id" in data
    assert "created_at" in data


def test_list_cases(client: TestClient) -> None:
    """Test listing cases."""
    client.post(
        "/api/cases",
        json={"pet_species": "cat", "pet_breed": "siamese", "study_type": "ct-scan"},
    )
    response = client.get("/api/cases")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1


def test_get_case(client: TestClient) -> None:
    """Test getting a specific case."""
    response = client.post(
        "/api/cases",
        json={"pet_species": "bird", "pet_breed": "parrot", "study_type": "ultrasound"},
    )
    assert response.status_code == 201
    case_id = response.json()["id"]

    response = client.get(f"/api/cases/{case_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == case_id
    assert data["pet_species"] == "bird"


def test_get_nonexistent_case(client: TestClient) -> None:
    """Test getting a case that doesn't exist."""
    response = client.get("/api/cases/00000000-0000-0000-0000-000000000999")
    assert response.status_code == 404


def test_update_case(client: TestClient) -> None:
    """Test updating a case."""
    response = client.post(
        "/api/cases",
        json={"pet_species": "dog", "pet_breed": "poodle", "study_type": "mri"},
    )
    assert response.status_code == 201
    case_id = response.json()["id"]

    response = client.patch(f"/api/cases/{case_id}", json={"pet_breed": "goldendoodle"})
    assert response.status_code == 200
    data = response.json()
    assert data["pet_breed"] == "goldendoodle"
    assert data["pet_species"] == "dog"


def test_delete_case(client: TestClient) -> None:
    """Test deleting a case."""
    response = client.post(
        "/api/cases",
        json={"pet_species": "rabbit", "pet_breed": "holland lop", "study_type": "x-ray"},
    )
    assert response.status_code == 201
    case_id = response.json()["id"]

    response = client.delete(f"/api/cases/{case_id}")
    assert response.status_code == 200
    assert "message" in response.json()

    response = client.get(f"/api/cases/{case_id}")
    assert response.status_code == 404
