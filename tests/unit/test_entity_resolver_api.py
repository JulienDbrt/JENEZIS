#!/usr/bin/env python3
"""
Comprehensive unit tests for the Entity Resolver API.
Tests entity resolution, caching, enrichment queue, and admin endpoints.
"""

import sqlite3
from pathlib import Path

import pytest


class TestEntityResolverAPI:
    """Test suite for Entity Resolver API endpoints and functionality."""

    # ========================================================================
    # Test root endpoint
    # ========================================================================

    @pytest.mark.unit
    @pytest.mark.api
    def test_root_endpoint(self, entity_resolver_client):
        """Test the root endpoint returns service information."""
        response = entity_resolver_client.get("/")

        assert response.status_code == 200
        data = response.json()

        assert data["service"] == "Entity Resolver API"
        assert data["version"] == "1.0.0"
        assert "cache_size" in data
        assert "endpoints" in data
        assert len(data["endpoints"]) > 0

    # ========================================================================
    # Test /resolve endpoint
    # ========================================================================

    @pytest.mark.unit
    @pytest.mark.api
    def test_resolve_known_companies(self, entity_resolver_client):
        """Test resolution of known company names."""
        response = entity_resolver_client.post(
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
        assert data["results"][0]["display_name"] == "Google"
        assert data["results"][0]["is_known"] is True
        assert data["results"][0]["entity_type"] == "COMPANY"

        # Check Microsoft resolution
        assert data["results"][1]["original_name"] == "Microsoft Corp"
        assert data["results"][1]["canonical_id"] == "microsoft"
        assert data["results"][1]["display_name"] == "Microsoft Corporation"

        # Check BNP resolution
        assert data["results"][2]["original_name"] == "BNP"
        assert data["results"][2]["canonical_id"] == "bnp_paribas"
        assert data["results"][2]["display_name"] == "BNP Paribas"

        # Check stats
        assert data["stats"]["total"] == 3
        assert data["stats"]["known"] == 3
        assert data["stats"]["unknown"] == 0

    @pytest.mark.unit
    @pytest.mark.api
    def test_resolve_known_schools(self, entity_resolver_client):
        """Test resolution of known school names."""
        response = entity_resolver_client.post(
            "/resolve", json={"entities": ["MIT", "Polytechnique", "X"], "entity_type": "SCHOOL"}
        )

        assert response.status_code == 200
        data = response.json()

        assert len(data["results"]) == 3

        # Check MIT resolution
        assert data["results"][0]["canonical_id"] == "mit"
        assert data["results"][0]["display_name"] == "MIT"
        assert data["results"][0]["entity_type"] == "SCHOOL"

        # Check Polytechnique resolution
        assert data["results"][1]["canonical_id"] == "ecole_polytechnique"
        assert data["results"][1]["display_name"] == "École Polytechnique"

        # Check X (alias for Polytechnique)
        assert data["results"][2]["canonical_id"] == "ecole_polytechnique"

    @pytest.mark.unit
    @pytest.mark.api
    def test_resolve_unknown_entities(self, entity_resolver_client):
        """Test resolution of unknown entities."""
        response = entity_resolver_client.post(
            "/resolve", json={"entities": ["Unknown Corp", "Startup XYZ"], "entity_type": "COMPANY"}
        )

        assert response.status_code == 200
        data = response.json()

        assert len(data["results"]) == 2

        # Check unknown entity handling
        assert data["results"][0]["original_name"] == "Unknown Corp"
        assert data["results"][0]["canonical_id"] == "unknown_corp"
        assert data["results"][0]["display_name"] == "Unknown Corp"
        assert data["results"][0]["is_known"] is False
        assert data["results"][0]["entity_type"] == "COMPANY"

        assert data["results"][1]["canonical_id"] == "startup_xyz"
        assert data["results"][1]["is_known"] is False

        # Check stats
        assert data["stats"]["known"] == 0
        assert data["stats"]["unknown"] == 2
        assert data["stats"]["queued_for_enrichment"] == 2

    @pytest.mark.unit
    @pytest.mark.api
    def test_resolve_mixed_entities(self, entity_resolver_client):
        """Test resolution with mix of known and unknown entities."""
        response = entity_resolver_client.post(
            "/resolve",
            json={"entities": ["Google", "Unknown Tech", "Microsoft"], "entity_type": "COMPANY"},
        )

        assert response.status_code == 200
        data = response.json()

        assert data["stats"]["total"] == 3
        assert data["stats"]["known"] == 2
        assert data["stats"]["unknown"] == 1

    @pytest.mark.unit
    @pytest.mark.api
    def test_resolve_empty_entities(self, entity_resolver_client):
        """Test resolution with empty entity list."""
        response = entity_resolver_client.post(
            "/resolve", json={"entities": [], "entity_type": "COMPANY"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["results"] == []
        assert data["stats"]["total"] == 0

    @pytest.mark.unit
    @pytest.mark.api
    def test_resolve_with_empty_strings(self, entity_resolver_client):
        """Test resolution handles empty strings gracefully."""
        response = entity_resolver_client.post(
            "/resolve",
            json={"entities": ["Google", "", "  ", "Microsoft"], "entity_type": "COMPANY"},
        )

        assert response.status_code == 200
        data = response.json()

        # Empty strings should be filtered out
        assert len(data["results"]) == 2
        assert data["results"][0]["original_name"] == "Google"
        assert data["results"][1]["original_name"] == "Microsoft"

    @pytest.mark.unit
    @pytest.mark.api
    def test_resolve_case_insensitive(self, entity_resolver_client):
        """Test that resolution is case-insensitive."""
        response = entity_resolver_client.post(
            "/resolve",
            json={"entities": ["GOOGLE", "Google", "google", "GoOgLe"], "entity_type": "COMPANY"},
        )

        assert response.status_code == 200
        data = response.json()

        # All variations should resolve to same entity
        for result in data["results"]:
            assert result["canonical_id"] == "google"
            assert result["is_known"] is True

    @pytest.mark.unit
    @pytest.mark.api
    def test_resolve_partial_match(self, entity_resolver_client):
        """Test partial matching for entity resolution."""
        response = entity_resolver_client.post(
            "/resolve",
            json={"entities": ["Google Inc", "Microsoft Corporation"], "entity_type": "COMPANY"},
        )

        assert response.status_code == 200
        data = response.json()

        # Should match based on partial containment
        assert data["results"][0]["canonical_id"] == "google"
        assert data["results"][1]["canonical_id"] == "microsoft"

    @pytest.mark.unit
    @pytest.mark.api
    def test_resolve_special_characters_in_name(self, entity_resolver_client):
        """Test entity names with special characters."""
        response = entity_resolver_client.post(
            "/resolve",
            json={
                "entities": ["Company & Co.", "Start-up #1", "Entity's Name"],
                "entity_type": "COMPANY",
            },
        )

        assert response.status_code == 200
        data = response.json()

        # Should generate clean canonical IDs
        assert data["results"][0]["canonical_id"] == "company__co"
        assert data["results"][1]["canonical_id"] == "startup_1"
        assert data["results"][2]["canonical_id"] == "entitys_name"

    # ========================================================================
    # Test /stats endpoint
    # ========================================================================

    @pytest.mark.unit
    @pytest.mark.api
    def test_stats_endpoint(self, entity_resolver_client):
        """Test the statistics endpoint."""
        response = entity_resolver_client.get("/stats")

        assert response.status_code == 200
        data = response.json()

        assert "cache_size" in data
        assert "entities" in data
        assert "total_aliases" in data
        assert "enrichment_queue" in data
        assert "database" in data

        # Check entity counts by type
        assert "COMPANY" in data["entities"]
        assert "SCHOOL" in data["entities"]
        assert data["entities"]["COMPANY"] == 3  # Based on test fixture
        assert data["entities"]["SCHOOL"] == 2  # Based on test fixture
        assert data["total_aliases"] == 12  # Based on test fixture

    @pytest.mark.unit
    @pytest.mark.api
    def test_stats_with_missing_db(self, entity_resolver_client, monkeypatch):
        """Test stats endpoint when database is missing."""
        import entity_resolver.api

        original_db = entity_resolver.api.DB_FILE
        entity_resolver.api.DB_FILE = "/non/existent/db.db"

        response = entity_resolver_client.get("/stats")

        assert response.status_code == 200
        data = response.json()
        assert data == {"error": "Database not found"}

        # Restore original
        entity_resolver.api.DB_FILE = original_db

    # ========================================================================
    # Test /enrichment/queue endpoint
    # ========================================================================

    @pytest.mark.unit
    @pytest.mark.api
    def test_enrichment_queue_empty(self, entity_resolver_client):
        """Test enrichment queue endpoint with empty queue."""
        response = entity_resolver_client.get("/enrichment/queue")

        assert response.status_code == 200
        data = response.json()

        assert "queue" in data
        assert "count" in data
        assert data["count"] == 0

    @pytest.mark.unit
    @pytest.mark.api
    def test_enrichment_queue_after_unknown_entities(self, entity_resolver_client, temp_entity_db):
        """Test that unknown entities are added to enrichment queue."""
        # First resolve some unknown entities
        entity_resolver_client.post(
            "/resolve", json={"entities": ["NewCompany1", "NewCompany2"], "entity_type": "COMPANY"}
        )

        # Check the queue
        response = entity_resolver_client.get("/enrichment/queue")

        assert response.status_code == 200
        data = response.json()

        assert data["count"] == 2
        queue_ids = [item["canonical_id"] for item in data["queue"]]
        assert "newcompany1" in queue_ids
        assert "newcompany2" in queue_ids

        # All should be PENDING
        for item in data["queue"]:
            assert item["status"] == "PENDING"
            assert item["entity_type"] == "COMPANY"

    @pytest.mark.unit
    @pytest.mark.api
    def test_enrichment_queue_no_duplicates(self, entity_resolver_client):
        """Test that entities are not duplicated in enrichment queue."""
        # Resolve same unknown entity multiple times
        for _ in range(3):
            entity_resolver_client.post(
                "/resolve", json={"entities": ["UniqueNewCompany"], "entity_type": "COMPANY"}
            )

        # Check the queue
        response = entity_resolver_client.get("/enrichment/queue")
        data = response.json()

        # Should only have one entry
        queue_ids = [item["canonical_id"] for item in data["queue"]]
        assert queue_ids.count("uniquenewcompany") == 1

    # ========================================================================
    # Test /admin/reload endpoint
    # ========================================================================

    @pytest.mark.unit
    @pytest.mark.api
    def test_admin_reload_cache(self, entity_resolver_client, temp_entity_db, auth_headers):
        """Test cache reload functionality."""
        # Initial reload
        response = entity_resolver_client.post("/admin/reload", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "Cache reloaded"
        initial_size = data["cache_size"]

        # Add new entity to database
        conn = sqlite3.connect(temp_entity_db)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO canonical_entities (canonical_id, display_name, entity_type) VALUES (?, ?, ?)",
            ("new_company", "New Company", "COMPANY"),
        )
        entity_id = cursor.lastrowid
        cursor.execute(
            "INSERT INTO entity_aliases (alias_name, canonical_id) VALUES (?, ?)",
            ("new company", entity_id),
        )
        conn.commit()
        conn.close()

        # Reload cache
        response = entity_resolver_client.post("/admin/reload", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["cache_size"] == initial_size + 1

    # ========================================================================
    # Test /admin/add_entity endpoint
    # ========================================================================

    @pytest.mark.unit
    @pytest.mark.api
    def test_admin_add_entity_success(self, entity_resolver_client, auth_headers):
        """Test adding a new entity via admin endpoint."""
        response = entity_resolver_client.post(
            "/admin/add_entity",
            json={
                "canonical_id": "test_company",
                "display_name": "Test Company Inc.",
                "aliases": ["test co", "test company", "tci"],
                "entity_type": "COMPANY",
                "metadata": {"sector": "Technology", "founded": "2024"},
            },
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "success"
        assert data["canonical_id"] == "test_company"
        assert data["aliases_added"] == 3
        assert data["cache_reloaded"] is True

        # Verify the entity can be resolved
        resolve_response = entity_resolver_client.post(
            "/resolve", json={"entities": ["test co"], "entity_type": "COMPANY"}
        )

        assert resolve_response.status_code == 200
        resolve_data = resolve_response.json()
        assert resolve_data["results"][0]["canonical_id"] == "test_company"
        assert resolve_data["results"][0]["display_name"] == "Test Company Inc."

    @pytest.mark.unit
    @pytest.mark.api
    def test_admin_add_entity_duplicate(self, entity_resolver_client, auth_headers):
        """Test adding duplicate entity returns error."""
        # Add entity first time
        entity_resolver_client.post(
            "/admin/add_entity",
            json={
                "canonical_id": "duplicate_test",
                "display_name": "Duplicate Test",
                "aliases": ["dup test"],
                "entity_type": "COMPANY",
            },
            headers=auth_headers,
        )

        # Try to add again
        response = entity_resolver_client.post(
            "/admin/add_entity",
            json={
                "canonical_id": "duplicate_test",
                "display_name": "Duplicate Test",
                "aliases": ["another alias"],
                "entity_type": "COMPANY",
            },
            headers=auth_headers,
        )

        assert response.status_code == 400
        assert "already exists" in response.json()["detail"]

    @pytest.mark.unit
    @pytest.mark.api
    def test_admin_add_entity_with_existing_alias(self, entity_resolver_client, auth_headers):
        """Test that duplicate aliases are handled gracefully."""
        response = entity_resolver_client.post(
            "/admin/add_entity",
            json={
                "canonical_id": "new_google",
                "display_name": "New Google",
                "aliases": ["google", "new google"],  # "google" already exists
                "entity_type": "COMPANY",
            },
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        # Should add only the new alias
        assert data["aliases_added"] == 1

    @pytest.mark.unit
    @pytest.mark.api
    def test_admin_add_entity_no_db(self, entity_resolver_client, auth_headers, monkeypatch):
        """Test add entity when database doesn't exist."""
        import entity_resolver.api

        original_db = entity_resolver.api.DB_FILE
        entity_resolver.api.DB_FILE = "/non/existent/db.db"

        response = entity_resolver_client.post(
            "/admin/add_entity",
            json={
                "canonical_id": "test",
                "display_name": "Test",
                "aliases": ["test"],
                "entity_type": "COMPANY",
            },
            headers=auth_headers,
        )

        assert response.status_code == 500
        assert "Database not found" in response.json()["detail"]

        # Restore
        entity_resolver.api.DB_FILE = original_db

    # ========================================================================
    # Test error handling
    # ========================================================================

    @pytest.mark.unit
    @pytest.mark.api
    def test_resolve_invalid_request(self, entity_resolver_client):
        """Test resolve endpoint with invalid request."""
        # Missing required field
        response = entity_resolver_client.post("/resolve", json={})
        assert response.status_code == 422

        # Wrong type for entities
        response = entity_resolver_client.post(
            "/resolve", json={"entities": "not_a_list", "entity_type": "COMPANY"}
        )
        assert response.status_code == 422

    # ========================================================================
    # Test cache mechanisms
    # ========================================================================

    @pytest.mark.unit
    def test_cache_loading_with_empty_db(self, monkeypatch):
        """Test cache loading with empty database."""
        import tempfile

        from entity_resolver.api import load_cache

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            temp_db = f.name

        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()

        # Create empty tables
        cursor.execute(
            """CREATE TABLE canonical_entities (
            id INTEGER PRIMARY KEY,
            canonical_id TEXT,
            display_name TEXT,
            entity_type TEXT,
            metadata TEXT
        )"""
        )
        cursor.execute(
            """CREATE TABLE entity_aliases (
            id INTEGER PRIMARY KEY,
            alias_name TEXT,
            canonical_id INTEGER
        )"""
        )
        conn.commit()
        conn.close()

        import entity_resolver.api

        entity_resolver.api.DB_FILE = temp_db

        # Load cache - should handle empty DB
        load_cache()

        assert len(entity_resolver.api.ENTITY_CACHE) == 0

        Path(temp_db).unlink()

    @pytest.mark.unit
    def test_cache_loading_with_missing_db(self, capsys):
        """Test cache loading when database doesn't exist."""
        import entity_resolver.api
        from entity_resolver.api import load_cache

        entity_resolver.api.DB_FILE = "/non/existent/database.db"

        # Should handle gracefully
        load_cache()

        captured = capsys.readouterr()
        assert "introuvable" in captured.out
        assert entity_resolver.api.ENTITY_CACHE == {}

    # ========================================================================
    # Test entity resolution logic
    # ========================================================================

    @pytest.mark.unit
    def test_resolve_entity_function(self):
        """Test the resolve_entity function directly."""
        from src.entity_resolver.api import ENTITY_CACHE, resolve_entity

        # Set up test cache
        ENTITY_CACHE["test company"] = {
            "canonical_id": "test_co",
            "display_name": "Test Company",
            "entity_type": "COMPANY",
            "metadata": {},
        }

        # Test exact match
        result = resolve_entity("Test Company")
        assert result["canonical_id"] == "test_co"
        assert result["is_known"] is True

        # Test partial match
        result = resolve_entity("test company inc")
        assert result["canonical_id"] == "test_co"

        # Test unknown entity
        result = resolve_entity("Unknown Entity")
        assert result["canonical_id"] == "unknown_entity"
        assert result["is_known"] is False

        # Test with preferred type
        result = resolve_entity("test company", preferred_type="SCHOOL")
        # Should not match since type doesn't match
        assert result["is_known"] is False
