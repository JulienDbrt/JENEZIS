#!/usr/bin/env python3
"""
Comprehensive unit tests for the Entity Resolver API.
Tests entity resolution, caching, enrichment queue, and admin endpoints.
"""

import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def api_client(monkeypatch):
    """Create a test client for the Entity Resolver API with mocked database."""
    os.environ["API_AUTH_TOKEN"] = "test_token_123"

    import entity_resolver.api
    from entity_resolver.api import app

    # Set up test entity cache
    entity_resolver.api.ENTITY_ALIAS_CACHE = {
        "google": {"canonical_id": "google", "canonical_name": "Google", "entity_type": "COMPANY"},
        "google inc": {"canonical_id": "google", "canonical_name": "Google", "entity_type": "COMPANY"},
        "google llc": {"canonical_id": "google", "canonical_name": "Google", "entity_type": "COMPANY"},
        "microsoft": {"canonical_id": "microsoft", "canonical_name": "Microsoft Corporation", "entity_type": "COMPANY"},
        "microsoft corp": {"canonical_id": "microsoft", "canonical_name": "Microsoft Corporation", "entity_type": "COMPANY"},
        "msft": {"canonical_id": "microsoft", "canonical_name": "Microsoft Corporation", "entity_type": "COMPANY"},
        "bnp": {"canonical_id": "bnp_paribas", "canonical_name": "BNP Paribas", "entity_type": "COMPANY"},
        "bnp paribas": {"canonical_id": "bnp_paribas", "canonical_name": "BNP Paribas", "entity_type": "COMPANY"},
        "polytechnique": {"canonical_id": "ecole_polytechnique", "canonical_name": "École Polytechnique", "entity_type": "SCHOOL"},
        "x": {"canonical_id": "ecole_polytechnique", "canonical_name": "École Polytechnique", "entity_type": "SCHOOL"},
        "massachusetts institute of technology": {"canonical_id": "mit", "canonical_name": "MIT", "entity_type": "SCHOOL"},
        "mit": {"canonical_id": "mit", "canonical_name": "MIT", "entity_type": "SCHOOL"},
    }
    entity_resolver.api.CANONICAL_ENTITIES = {
        "google": {"canonical_name": "Google", "entity_type": "COMPANY"},
        "microsoft": {"canonical_name": "Microsoft Corporation", "entity_type": "COMPANY"},
        "bnp_paribas": {"canonical_name": "BNP Paribas", "entity_type": "COMPANY"},
        "ecole_polytechnique": {"canonical_name": "École Polytechnique", "entity_type": "SCHOOL"},
        "mit": {"canonical_name": "MIT", "entity_type": "SCHOOL"},
    }

    from api.auth import auth
    auth.auth_token = "test_token_123"
    auth.is_enabled = True

    return TestClient(app)


@pytest.fixture
def auth_headers():
    """Authentication headers for admin endpoints."""
    return {"Authorization": "Bearer test_token_123"}


class TestEntityResolverAPI:
    """Test suite for Entity Resolver API endpoints and functionality."""

    # ========================================================================
    # Test /health endpoint
    # ========================================================================

    @pytest.mark.unit
    @pytest.mark.api
    def test_health_endpoint(self, api_client):
        """Test the health endpoint returns service information."""
        response = api_client.get("/health")

        assert response.status_code == 200
        data = response.json()

        assert "status" in data
        assert data["status"] in ["healthy", "degraded"]
        assert "database" in data

    # ========================================================================
    # Test /resolve endpoint
    # ========================================================================

    @pytest.mark.unit
    @pytest.mark.api
    def test_resolve_known_companies(self, api_client):
        """Test resolution of known company names."""
        # Mock the database for enrichment queue
        with patch("entity_resolver.api.get_db") as mock_get_db:
            mock_db = MagicMock()
            mock_get_db.return_value = iter([mock_db])

            response = api_client.post(
                "/resolve",
                json={"entities": ["Google", "Microsoft Corp", "BNP"], "entity_type": "COMPANY"},
            )

        assert response.status_code == 200
        data = response.json()

        assert "results" in data
        assert len(data["results"]) == 3

        # Check Google resolution
        assert data["results"][0]["original_name"] == "Google"
        assert data["results"][0]["canonical_id"] == "google"
        assert data["results"][0]["canonical_name"] == "Google"
        assert data["results"][0]["is_known"] is True
        assert data["results"][0]["entity_type"] == "COMPANY"

        # Check Microsoft resolution
        assert data["results"][1]["original_name"] == "Microsoft Corp"
        assert data["results"][1]["canonical_id"] == "microsoft"
        assert data["results"][1]["canonical_name"] == "Microsoft Corporation"

        # Check BNP resolution
        assert data["results"][2]["original_name"] == "BNP"
        assert data["results"][2]["canonical_id"] == "bnp_paribas"
        assert data["results"][2]["canonical_name"] == "BNP Paribas"

    @pytest.mark.unit
    @pytest.mark.api
    def test_resolve_known_schools(self, api_client):
        """Test resolution of known school names."""
        with patch("entity_resolver.api.get_db") as mock_get_db:
            mock_db = MagicMock()
            mock_get_db.return_value = iter([mock_db])

            response = api_client.post(
                "/resolve", json={"entities": ["MIT", "Polytechnique", "X"], "entity_type": "SCHOOL"}
            )

        assert response.status_code == 200
        data = response.json()

        assert len(data["results"]) == 3

        # Check MIT resolution
        assert data["results"][0]["canonical_id"] == "mit"
        assert data["results"][0]["canonical_name"] == "MIT"
        assert data["results"][0]["entity_type"] == "SCHOOL"

        # Check Polytechnique resolution
        assert data["results"][1]["canonical_id"] == "ecole_polytechnique"
        assert data["results"][1]["canonical_name"] == "École Polytechnique"

        # Check X (alias for Polytechnique)
        assert data["results"][2]["canonical_id"] == "ecole_polytechnique"

    @pytest.mark.unit
    @pytest.mark.api
    def test_resolve_unknown_entities(self, api_client):
        """Test resolution of unknown entities."""
        with patch("entity_resolver.api.get_db") as mock_get_db:
            mock_db = MagicMock()
            mock_get_db.return_value = iter([mock_db])

            response = api_client.post(
                "/resolve", json={"entities": ["Unknown Corp", "Startup XYZ"], "entity_type": "COMPANY"}
            )

        assert response.status_code == 200
        data = response.json()

        assert len(data["results"]) == 2

        # Check unknown entity handling
        assert data["results"][0]["original_name"] == "Unknown Corp"
        assert data["results"][0]["is_known"] is False
        assert data["results"][0]["entity_type"] == "COMPANY"

        assert data["results"][1]["is_known"] is False

    @pytest.mark.unit
    @pytest.mark.api
    def test_resolve_mixed_entities(self, api_client):
        """Test resolution with mix of known and unknown entities."""
        with patch("entity_resolver.api.get_db") as mock_get_db:
            mock_db = MagicMock()
            mock_get_db.return_value = iter([mock_db])

            response = api_client.post(
                "/resolve",
                json={"entities": ["Google", "Unknown Tech", "Microsoft"], "entity_type": "COMPANY"},
            )

        assert response.status_code == 200
        data = response.json()

        assert len(data["results"]) == 3
        known_count = sum(1 for r in data["results"] if r["is_known"])
        assert known_count == 2

    @pytest.mark.unit
    @pytest.mark.api
    def test_resolve_empty_entities(self, api_client):
        """Test resolution with empty entity list."""
        with patch("entity_resolver.api.get_db") as mock_get_db:
            mock_db = MagicMock()
            mock_get_db.return_value = iter([mock_db])

            response = api_client.post(
                "/resolve", json={"entities": [], "entity_type": "COMPANY"}
            )

        assert response.status_code == 200
        data = response.json()
        assert data["results"] == []

    @pytest.mark.unit
    @pytest.mark.api
    def test_resolve_case_insensitive(self, api_client):
        """Test that resolution is case-insensitive."""
        with patch("entity_resolver.api.get_db") as mock_get_db:
            mock_db = MagicMock()
            mock_get_db.return_value = iter([mock_db])

            response = api_client.post(
                "/resolve",
                json={"entities": ["GOOGLE", "Google", "google", "GoOgLe"], "entity_type": "COMPANY"},
            )

        assert response.status_code == 200
        data = response.json()

        # All variations should resolve to same entity
        for result in data["results"]:
            assert result["canonical_id"] == "google"
            assert result["is_known"] is True

    # ========================================================================
    # Test /stats endpoint
    # ========================================================================

    @pytest.mark.unit
    @pytest.mark.api
    def test_stats_endpoint(self, api_client):
        """Test the statistics endpoint."""
        with patch("entity_resolver.api.get_db") as mock_get_db:
            mock_db = MagicMock()
            mock_get_db.return_value = iter([mock_db])
            mock_db.execute.return_value.scalar.side_effect = [3, 2, 12, 0]

            response = api_client.get("/stats")

        assert response.status_code == 200
        data = response.json()

        assert "total_companies" in data
        assert "total_schools" in data
        assert "total_aliases" in data
        assert "database" in data

    # ========================================================================
    # Test /enrichment/queue endpoint
    # ========================================================================

    @pytest.mark.unit
    @pytest.mark.api
    def test_enrichment_queue_endpoint(self, api_client):
        """Test enrichment queue endpoint."""
        with patch("entity_resolver.api.get_db") as mock_get_db:
            mock_db = MagicMock()
            mock_get_db.return_value = iter([mock_db])
            mock_db.execute.return_value = []

            response = api_client.get("/enrichment/queue")

        assert response.status_code == 200
        data = response.json()

        assert "queue" in data

    # ========================================================================
    # Test /admin/reload endpoint
    # ========================================================================

    @pytest.mark.unit
    @pytest.mark.api
    def test_admin_reload_cache(self, api_client, auth_headers):
        """Test cache reload functionality."""
        with patch("entity_resolver.api.SessionLocal") as mock_session:
            mock_db = MagicMock()
            mock_session.return_value = mock_db
            mock_db.execute.return_value = []

            response = api_client.post("/admin/reload", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "message" in data

    # ========================================================================
    # Test /admin/add_entity endpoint
    # ========================================================================

    @pytest.mark.unit
    @pytest.mark.api
    def test_admin_add_entity_success(self, api_client, auth_headers):
        """Test adding a new entity via admin endpoint."""
        with patch("entity_resolver.api.get_db") as mock_get_db:
            mock_db = MagicMock()
            mock_get_db.return_value = iter([mock_db])

            with patch("entity_resolver.api.SessionLocal") as mock_session:
                mock_session.return_value = mock_db

                response = api_client.post(
                    "/admin/add_entity",
                    params={
                        "canonical_name": "Test Company Inc.",
                        "entity_type": "COMPANY",
                    },
                    headers=auth_headers,
                )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "canonical_id" in data

    # ========================================================================
    # Test error handling
    # ========================================================================

    @pytest.mark.unit
    @pytest.mark.api
    def test_resolve_invalid_request(self, api_client):
        """Test resolve endpoint with invalid request."""
        # Missing required field
        response = api_client.post("/resolve", json={})
        assert response.status_code == 422

        # Wrong type for entities
        response = api_client.post(
            "/resolve", json={"entities": "not_a_list", "entity_type": "COMPANY"}
        )
        assert response.status_code == 422

    # ========================================================================
    # Test cache loading
    # ========================================================================

    @pytest.mark.unit
    def test_load_entity_cache_handles_db_error(self, monkeypatch):
        """Test that load_entity_cache handles database errors gracefully."""
        import entity_resolver.api
        from entity_resolver.api import load_entity_cache

        # Clear cache first
        entity_resolver.api.ENTITY_ALIAS_CACHE = {}
        entity_resolver.api.CANONICAL_ENTITIES = {}

        with patch("entity_resolver.api.SessionLocal") as mock_session:
            mock_db = MagicMock()
            mock_session.return_value = mock_db
            mock_db.execute.side_effect = Exception("Database connection error")

            # Should handle error gracefully
            load_entity_cache()

        # Caches should remain empty or unchanged
        assert isinstance(entity_resolver.api.ENTITY_ALIAS_CACHE, dict)
        assert isinstance(entity_resolver.api.CANONICAL_ENTITIES, dict)

    @pytest.mark.unit
    def test_load_entity_cache_success(self, monkeypatch):
        """Test successful cache loading."""
        import entity_resolver.api
        from entity_resolver.api import load_entity_cache

        with patch("entity_resolver.api.SessionLocal") as mock_session:
            mock_db = MagicMock()
            mock_session.return_value = mock_db

            # Mock queries
            mock_db.execute.return_value = []

            load_entity_cache()

        # Should complete without error
        assert True

    # ========================================================================
    # Test authentication
    # ========================================================================

    @pytest.mark.unit
    @pytest.mark.api
    def test_admin_endpoint_requires_auth(self, api_client):
        """Test that admin endpoints require authentication."""
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
