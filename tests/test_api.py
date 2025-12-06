#!/usr/bin/env python3
"""
Basic API tests for the Harmonizer API.
"""

import os
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch):
    """Create a test client with mocked database caches."""
    os.environ["API_AUTH_TOKEN"] = "test_token_123"

    # Import API module and set up test caches
    import api.main
    from api.main import app

    # Set up test data in caches
    api.main.ALIAS_CACHE = {
        "python": "python",
        "py": "python",
        "javascript": "javascript",
        "js": "javascript",
    }
    api.main.SKILLS_CACHE = {
        "python": 1,
        "javascript": 2,
    }
    api.main.HIERARCHY_CACHE = {}

    # Set up auth
    from api.auth import auth
    auth.auth_token = "test_token_123"
    auth.is_enabled = True

    return TestClient(app)


@pytest.fixture
def auth_headers():
    """Headers d'authentification pour les tests admin."""
    return {"Authorization": "Bearer test_token_123"}


@pytest.mark.unit
@pytest.mark.api
def test_harmonize_known_skills(client):
    """Test avec des compétences connues."""
    response = client.post("/harmonize", json={"skills": ["Python", "JS", "py"]})
    assert response.status_code == 200
    data = response.json()

    assert len(data["results"]) == 3
    assert data["results"][0]["canonical_skill"] == "python"
    assert data["results"][0]["is_known"] is True
    assert data["results"][1]["canonical_skill"] == "javascript"
    assert data["results"][1]["is_known"] is True
    assert data["results"][2]["canonical_skill"] == "python"
    assert data["results"][2]["is_known"] is True


@pytest.mark.unit
@pytest.mark.api
def test_harmonize_unknown_skills(client):
    """Test avec des compétences inconnues."""
    response = client.post("/harmonize", json={"skills": ["rust", "golang"]})
    assert response.status_code == 200
    data = response.json()

    assert len(data["results"]) == 2
    assert data["results"][0]["canonical_skill"] == "rust"
    assert data["results"][0]["is_known"] is False
    assert data["results"][1]["canonical_skill"] == "golang"
    assert data["results"][1]["is_known"] is False


@pytest.mark.unit
@pytest.mark.api
def test_harmonize_mixed_skills(client):
    """Test avec un mix de compétences."""
    response = client.post("/harmonize", json={"skills": ["python", "unknown_skill", "js"]})
    assert response.status_code == 200
    data = response.json()

    assert len(data["results"]) == 3
    assert data["results"][0]["is_known"] is True
    assert data["results"][1]["is_known"] is False
    assert data["results"][2]["is_known"] is True


@pytest.mark.unit
@pytest.mark.api
def test_reload_cache(client, auth_headers):
    """Test du rechargement du cache."""
    # Mock the database session to avoid PostgreSQL connection
    from unittest.mock import patch, MagicMock

    with patch("api.main.SessionLocal") as mock_session:
        mock_db = MagicMock()
        mock_session.return_value = mock_db

        # Mock database queries to return empty results
        mock_db.execute.return_value = []

        response = client.post("/admin/reload", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "message" in data


@pytest.mark.unit
@pytest.mark.api
def test_stats_endpoint(client):
    """Test de l'endpoint de statistiques."""
    # Mock the database dependency
    from unittest.mock import patch, MagicMock

    with patch("api.main.get_db") as mock_get_db:
        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])

        # Mock the scalar results for COUNT queries
        mock_db.execute.return_value.scalar.side_effect = [2, 4, 0]

        response = client.get("/stats")

    assert response.status_code == 200
    data = response.json()
    assert "total_skills" in data
    assert "total_aliases" in data
    assert "total_relations" in data


@pytest.mark.unit
@pytest.mark.api
def test_health_endpoint(client):
    """Test the health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert data["status"] in ["healthy", "degraded"]
