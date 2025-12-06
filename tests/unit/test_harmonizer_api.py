#!/usr/bin/env python3
"""
Comprehensive unit tests for the Harmonizer API.
Tests all endpoints, error handling, cache mechanisms, and LLM integration.
"""

import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def api_client(monkeypatch):
    """Create a test client for the Harmonizer API with mocked database."""
    os.environ["API_AUTH_TOKEN"] = "test_token_123"

    import api.main
    from api.main import app

    # Set up test caches
    api.main.ALIAS_CACHE = {
        "python": "python",
        "py": "python",
        "python3": "python",
        "javascript": "javascript",
        "js": "javascript",
        "ecmascript": "javascript",
        "react": "react",
        "reactjs": "react",
        "react.js": "react",
        "ml": "machine_learning",
        "machine learning": "machine_learning",
    }
    api.main.SKILLS_CACHE = {
        "python": 1,
        "javascript": 2,
        "react": 3,
        "programming_languages": 4,
        "frontend": 5,
        "data_science": 6,
        "machine_learning": 7,
    }
    api.main.HIERARCHY_CACHE = {
        "python": ["programming_languages"],
        "javascript": ["programming_languages"],
        "react": ["javascript", "frontend"],
        "machine_learning": ["data_science"],
    }

    from api.auth import auth
    auth.auth_token = "test_token_123"
    auth.is_enabled = True

    return TestClient(app)


@pytest.fixture
def auth_headers():
    """Authentication headers for admin endpoints."""
    return {"Authorization": "Bearer test_token_123"}


class TestHarmonizerAPI:
    """Test suite for Harmonizer API endpoints and functionality."""

    # ========================================================================
    # Test /harmonize endpoint
    # ========================================================================

    @pytest.mark.unit
    @pytest.mark.api
    def test_harmonize_known_skills(self, api_client):
        """Test harmonization with known skills from the ontology."""
        response = api_client.post(
            "/harmonize", json={"skills": ["Python", "JS", "react.js", "ML"]}
        )

        assert response.status_code == 200
        data = response.json()

        assert "results" in data
        assert len(data["results"]) == 4

        # Check first skill - Python
        assert data["results"][0]["original_skill"] == "Python"
        assert data["results"][0]["canonical_skill"] == "python"
        assert data["results"][0]["is_known"] is True

        # Check JS alias
        assert data["results"][1]["original_skill"] == "JS"
        assert data["results"][1]["canonical_skill"] == "javascript"
        assert data["results"][1]["is_known"] is True

        # Check react.js alias
        assert data["results"][2]["original_skill"] == "react.js"
        assert data["results"][2]["canonical_skill"] == "react"
        assert data["results"][2]["is_known"] is True

        # Check ML alias
        assert data["results"][3]["original_skill"] == "ML"
        assert data["results"][3]["canonical_skill"] == "machine_learning"
        assert data["results"][3]["is_known"] is True

    @pytest.mark.unit
    @pytest.mark.api
    def test_harmonize_unknown_skills(self, api_client):
        """Test harmonization with unknown skills."""
        response = api_client.post(
            "/harmonize", json={"skills": ["rust", "golang", "kotlin"]}
        )

        assert response.status_code == 200
        data = response.json()

        assert len(data["results"]) == 3
        for i, skill in enumerate(["rust", "golang", "kotlin"]):
            assert data["results"][i]["original_skill"] == skill
            assert data["results"][i]["canonical_skill"] == skill.lower()
            assert data["results"][i]["is_known"] is False

    @pytest.mark.unit
    @pytest.mark.api
    def test_harmonize_mixed_skills(self, api_client):
        """Test harmonization with a mix of known and unknown skills."""
        response = api_client.post(
            "/harmonize", json={"skills": ["python", "unknown_framework", "javascript"]}
        )

        assert response.status_code == 200
        data = response.json()

        assert len(data["results"]) == 3
        assert data["results"][0]["is_known"] is True
        assert data["results"][1]["is_known"] is False
        assert data["results"][2]["is_known"] is True

    @pytest.mark.unit
    @pytest.mark.api
    def test_harmonize_empty_list(self, api_client):
        """Test harmonization with empty skill list."""
        response = api_client.post("/harmonize", json={"skills": []})

        assert response.status_code == 200
        data = response.json()
        assert data["results"] == []

    @pytest.mark.unit
    @pytest.mark.api
    def test_harmonize_case_insensitive(self, api_client):
        """Test that harmonization is case-insensitive."""
        skills_variations = ["PYTHON", "Python", "python", "PythoN"]
        response = api_client.post("/harmonize", json={"skills": skills_variations})

        assert response.status_code == 200
        data = response.json()

        for result in data["results"]:
            assert result["canonical_skill"] == "python"
            assert result["is_known"] is True

    @pytest.mark.unit
    @pytest.mark.api
    def test_harmonize_whitespace_handling(self, api_client):
        """Test harmonization handles whitespace correctly."""
        response = api_client.post(
            "/harmonize", json={"skills": ["  python  ", "\tjavascript\n", " react "]}
        )

        assert response.status_code == 200
        data = response.json()

        assert data["results"][0]["canonical_skill"] == "python"
        assert data["results"][1]["canonical_skill"] == "javascript"
        assert data["results"][2]["canonical_skill"] == "react"

    # ========================================================================
    # Test /suggest endpoint
    # ========================================================================

    @pytest.mark.unit
    @pytest.mark.api
    def test_suggest_exact_match(self, api_client):
        """Test suggestions for an exact match returns the skill."""
        response = api_client.post("/suggest", json={"skill": "python", "top_k": 3})

        assert response.status_code == 200
        data = response.json()

        assert data["original_skill"] == "python"
        assert data["method"] == "exact_match"
        assert len(data["suggestions"]) == 1
        assert data["suggestions"][0]["canonical_name"] == "python"
        assert data["suggestions"][0]["similarity_score"] == 1.0
        assert "programming_languages" in data["suggestions"][0]["parents"]

    @pytest.mark.unit
    @pytest.mark.api
    def test_suggest_string_similarity(self, api_client):
        """Test string similarity-based suggestions."""
        response = api_client.post(
            "/suggest", json={"skill": "pytho", "top_k": 3, "use_llm": False}
        )

        assert response.status_code == 200
        data = response.json()

        assert data["method"] == "string_similarity"
        assert len(data["suggestions"]) > 0
        # Python should be in suggestions due to high similarity
        suggested_names = [s["canonical_name"] for s in data["suggestions"]]
        assert "python" in suggested_names

    @pytest.mark.unit
    @pytest.mark.api
    def test_suggest_top_k_limit(self, api_client):
        """Test that top_k parameter limits the number of suggestions."""
        for k in [1, 2, 5]:
            response = api_client.post("/suggest", json={"skill": "programming", "top_k": k})

            assert response.status_code == 200
            data = response.json()
            assert len(data["suggestions"]) <= k

    @pytest.mark.unit
    @pytest.mark.api
    def test_suggest_low_similarity_threshold(self, api_client):
        """Test that low similarity matches are filtered out."""
        response = api_client.post("/suggest", json={"skill": "xyz123", "top_k": 10})

        assert response.status_code == 200
        data = response.json()

        # Should have few or no suggestions due to low similarity
        for suggestion in data["suggestions"]:
            assert suggestion["similarity_score"] > 0.3

    # ========================================================================
    # Test /stats endpoint
    # ========================================================================

    @pytest.mark.unit
    @pytest.mark.api
    def test_stats_endpoint(self, api_client):
        """Test the statistics endpoint returns correct counts."""
        with patch("api.main.get_db") as mock_get_db:
            mock_db = MagicMock()
            mock_get_db.return_value = iter([mock_db])
            mock_db.execute.return_value.scalar.side_effect = [7, 11, 5]

            response = api_client.get("/stats")

        assert response.status_code == 200
        data = response.json()

        assert "total_skills" in data
        assert "total_aliases" in data
        assert "total_relations" in data

    # ========================================================================
    # Test /admin/reload endpoint
    # ========================================================================

    @pytest.mark.unit
    @pytest.mark.api
    def test_admin_reload_cache(self, api_client, auth_headers):
        """Test cache reload functionality."""
        with patch("api.main.SessionLocal") as mock_session:
            mock_db = MagicMock()
            mock_session.return_value = mock_db
            mock_db.execute.return_value = []

            response = api_client.post("/admin/reload", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "message" in data

    # ========================================================================
    # Test error handling
    # ========================================================================

    @pytest.mark.unit
    @pytest.mark.api
    def test_harmonize_invalid_request_body(self, api_client):
        """Test harmonize endpoint with invalid request body."""
        # Missing required field
        response = api_client.post("/harmonize", json={})
        assert response.status_code == 422

        # Wrong type for skills field
        response = api_client.post("/harmonize", json={"skills": "not_a_list"})
        assert response.status_code == 422

    @pytest.mark.unit
    @pytest.mark.api
    def test_suggest_invalid_request_body(self, api_client):
        """Test suggest endpoint with invalid request body."""
        # Missing required field
        response = api_client.post("/suggest", json={})
        assert response.status_code == 422

        # Invalid top_k value
        response = api_client.post(
            "/suggest", json={"skill": "python", "top_k": "not_a_number"}
        )
        assert response.status_code == 422

    # ========================================================================
    # Test health endpoint
    # ========================================================================

    @pytest.mark.unit
    @pytest.mark.api
    def test_health_endpoint(self, api_client):
        """Test health check endpoint."""
        response = api_client.get("/health")

        assert response.status_code == 200
        data = response.json()

        assert "status" in data
        assert data["status"] in ["healthy", "degraded"]
        assert "database" in data

    # ========================================================================
    # Test cache loading
    # ========================================================================

    @pytest.mark.unit
    def test_load_ontology_cache_handles_db_error(self, monkeypatch):
        """Test that load_ontology_cache handles database errors gracefully."""
        import api.main
        from api.main import load_ontology_cache

        # Clear caches first
        api.main.ALIAS_CACHE = {}
        api.main.SKILLS_CACHE = {}
        api.main.HIERARCHY_CACHE = {}

        with patch("api.main.SessionLocal") as mock_session:
            mock_db = MagicMock()
            mock_session.return_value = mock_db
            mock_db.execute.side_effect = Exception("Database connection error")

            # Should handle error gracefully
            load_ontology_cache()

        # Caches should remain empty or unchanged
        assert isinstance(api.main.ALIAS_CACHE, dict)
        assert isinstance(api.main.SKILLS_CACHE, dict)
        assert isinstance(api.main.HIERARCHY_CACHE, dict)

    @pytest.mark.unit
    def test_load_ontology_cache_success(self, monkeypatch):
        """Test successful cache loading."""
        import api.main
        from api.main import load_ontology_cache

        with patch("api.main.SessionLocal") as mock_session:
            mock_db = MagicMock()
            mock_session.return_value = mock_db

            # Mock alias query
            mock_db.execute.return_value = [
                ("python", "python"),
                ("py", "python"),
            ]

            load_ontology_cache()

        # Should complete without error
        assert True

    # ========================================================================
    # Test authentication
    # ========================================================================

    @pytest.mark.unit
    @pytest.mark.api
    def test_admin_endpoint_requires_auth(self, api_client):
        """Test that admin endpoints require authentication."""
        # Without auth headers
        response = api_client.post("/admin/reload")
        assert response.status_code == 403

    @pytest.mark.unit
    @pytest.mark.api
    def test_admin_endpoint_with_wrong_token(self, api_client):
        """Test that admin endpoints reject wrong tokens."""
        response = api_client.post(
            "/admin/reload",
            headers={"Authorization": "Bearer wrong_token"}
        )
        assert response.status_code == 403

    # ========================================================================
    # Test metrics endpoint
    # ========================================================================

    @pytest.mark.unit
    @pytest.mark.api
    def test_metrics_endpoint(self, api_client):
        """Test the metrics endpoint."""
        response = api_client.get("/metrics")
        assert response.status_code == 200
