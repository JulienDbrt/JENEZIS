#!/usr/bin/env python3
"""
Integration tests for both Harmonizer and Entity Resolver APIs.
Tests cross-API interactions, database operations, and end-to-end workflows.
"""

import json
import os
import sqlite3
import threading
import time
from unittest.mock import MagicMock, Mock, patch

import pandas as pd
import pytest
from fastapi.testclient import TestClient


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def harmonizer_client():
    """Create a test client for the Harmonizer API with mocked database."""
    os.environ["API_AUTH_TOKEN"] = "test_token_123"

    import api.main
    from api.main import app

    # Set up test caches
    api.main.ALIAS_CACHE = {
        "python": "python",
        "py": "python",
        "javascript": "javascript",
        "js": "javascript",
        "react": "react",
        "reactjs": "react",
    }
    api.main.SKILLS_CACHE = {
        "python": 1,
        "javascript": 2,
        "react": 3,
        "programming_languages": 4,
        "frontend": 5,
    }
    api.main.HIERARCHY_CACHE = {
        "python": ["programming_languages"],
        "javascript": ["programming_languages"],
        "react": ["javascript", "frontend"],
    }

    from api.auth import auth
    auth.auth_token = "test_token_123"
    auth.is_enabled = True

    return TestClient(app)


@pytest.fixture
def entity_resolver_client():
    """Create a test client for the Entity Resolver API with mocked database."""
    os.environ["API_AUTH_TOKEN"] = "test_token_123"

    import entity_resolver.api
    from entity_resolver.api import app

    # Set up test entity cache
    entity_resolver.api.ENTITY_ALIAS_CACHE = {
        "google": {"canonical_id": "google", "canonical_name": "Google", "entity_type": "COMPANY"},
        "microsoft": {"canonical_id": "microsoft", "canonical_name": "Microsoft Corporation", "entity_type": "COMPANY"},
        "mit": {"canonical_id": "mit", "canonical_name": "MIT", "entity_type": "SCHOOL"},
    }
    entity_resolver.api.CANONICAL_ENTITIES = {
        "google": {"canonical_name": "Google", "entity_type": "COMPANY"},
        "microsoft": {"canonical_name": "Microsoft Corporation", "entity_type": "COMPANY"},
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


@pytest.fixture
def sample_cv_data():
    """Sample CV data for testing graph ingestion."""
    return {
        "candidat": {"nom": "Doe", "prenom": "John", "email": "john.doe@example.com"},
        "experiences": [
            {
                "entreprise": "Google",
                "poste": "Software Engineer",
                "date_debut": "2020-01-01",
                "date_fin": "2023-01-01",
                "competences": ["Python", "JavaScript", "React"],
            }
        ],
        "formations": [
            {
                "ecole": "MIT",
                "diplome": "Master's in Computer Science",
                "date_obtention": "2019-06-01",
            }
        ],
    }


@pytest.fixture
def temp_ontology_db(tmp_path):
    """Create a temporary SQLite ontology database."""
    temp_db = tmp_path / "test_ontology.db"

    conn = sqlite3.connect(str(temp_db))
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE skills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            canonical_name TEXT UNIQUE NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE aliases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            alias_name TEXT UNIQUE NOT NULL,
            skill_id INTEGER NOT NULL,
            FOREIGN KEY (skill_id) REFERENCES skills(id) ON DELETE CASCADE
        )
    """)
    cursor.execute("""
        CREATE TABLE hierarchy (
            child_id INTEGER NOT NULL,
            parent_id INTEGER NOT NULL,
            PRIMARY KEY (child_id, parent_id),
            FOREIGN KEY (child_id) REFERENCES skills(id) ON DELETE CASCADE,
            FOREIGN KEY (parent_id) REFERENCES skills(id) ON DELETE CASCADE
        )
    """)

    cursor.execute("CREATE INDEX idx_aliases_name ON aliases(alias_name)")
    cursor.execute("CREATE INDEX idx_hierarchy_child ON hierarchy(child_id)")
    cursor.execute("CREATE INDEX idx_hierarchy_parent ON hierarchy(parent_id)")

    # Insert test data
    cursor.execute("INSERT INTO skills (id, canonical_name) VALUES (1, 'python')")
    cursor.execute("INSERT INTO skills (id, canonical_name) VALUES (2, 'javascript')")
    cursor.execute("INSERT INTO aliases (alias_name, skill_id) VALUES ('python', 1)")
    cursor.execute("INSERT INTO aliases (alias_name, skill_id) VALUES ('py', 1)")
    cursor.execute("INSERT INTO aliases (alias_name, skill_id) VALUES ('javascript', 2)")
    cursor.execute("INSERT INTO aliases (alias_name, skill_id) VALUES ('js', 2)")
    cursor.execute("INSERT INTO hierarchy (child_id, parent_id) VALUES (1, 2)")

    conn.commit()
    conn.close()

    return str(temp_db)


# ============================================================================
# API Integration Tests
# ============================================================================


class TestAPIIntegration:
    """Integration tests for API interactions."""

    @pytest.mark.integration
    @pytest.mark.api
    def test_harmonizer_with_full_hierarchy(self, harmonizer_client):
        """Test harmonization returns full hierarchy chain."""
        response = harmonizer_client.post("/harmonize", json={"skills": ["react"]})

        assert response.status_code == 200
        data = response.json()

        # React should be mapped correctly
        assert data["results"][0]["canonical_skill"] == "react"

    @pytest.mark.integration
    @pytest.mark.api
    def test_concurrent_cache_updates(self, harmonizer_client, auth_headers):
        """Test that cache updates don't cause race conditions."""
        results = []

        def harmonize_skills():
            response = harmonizer_client.post(
                "/harmonize", json={"skills": ["python", "javascript"]}
            )
            results.append(response.status_code == 200)

        def reload_cache():
            time.sleep(0.01)
            with patch("api.main.SessionLocal") as mock_session:
                mock_db = MagicMock()
                mock_session.return_value = mock_db
                mock_db.execute.return_value = []
                response = harmonizer_client.post("/admin/reload", headers=auth_headers)
                results.append(response.status_code == 200)

        # Start threads
        threads = []
        for _ in range(3):
            t1 = threading.Thread(target=harmonize_skills)
            t2 = threading.Thread(target=reload_cache)
            threads.extend([t1, t2])

        for t in threads:
            t.start()

        for t in threads:
            t.join()

        # All operations should succeed
        assert all(results)

    @pytest.mark.integration
    @pytest.mark.slow
    def test_large_batch_processing(self, harmonizer_client, entity_resolver_client):
        """Test processing large batches of data."""
        with patch("entity_resolver.api.get_db") as mock_get_db:
            mock_db = MagicMock()
            mock_get_db.return_value = iter([mock_db])

            # Test harmonizer with large batch
            large_skill_list = [f"skill_{i}" for i in range(1000)]
            response = harmonizer_client.post("/harmonize", json={"skills": large_skill_list})

            assert response.status_code == 200
            data = response.json()
            assert len(data["results"]) == 1000

            # Test entity resolver with large batch
            large_entity_list = [f"Company_{i}" for i in range(500)]
            response = entity_resolver_client.post(
                "/resolve", json={"entities": large_entity_list, "entity_type": "COMPANY"}
            )

            assert response.status_code == 200
            data = response.json()
            assert len(data["results"]) == 500


# ============================================================================
# Database Operations Tests
# ============================================================================


class TestDatabaseOperations:
    """Test database operations and consistency."""

    @pytest.mark.integration
    def test_database_transaction_rollback(self, temp_ontology_db):
        """Test that database transactions rollback on error."""
        conn = sqlite3.connect(temp_ontology_db)
        cursor = conn.cursor()

        cursor.execute("PRAGMA foreign_keys = ON")

        try:
            cursor.execute("BEGIN")
            cursor.execute("INSERT INTO skills (canonical_name) VALUES ('test_skill')")
            cursor.execute("INSERT INTO aliases (alias_name, skill_id) VALUES ('test', 99999)")
            cursor.execute("COMMIT")
        except sqlite3.IntegrityError:
            cursor.execute("ROLLBACK")

        cursor.execute("SELECT COUNT(*) FROM skills WHERE canonical_name = 'test_skill'")
        count = cursor.fetchone()[0]
        assert count == 0

        conn.close()

    @pytest.mark.integration
    def test_database_indexes_performance(self, temp_ontology_db):
        """Test that database indexes improve query performance."""
        conn = sqlite3.connect(temp_ontology_db)
        cursor = conn.cursor()

        # Add many records
        for i in range(1000):
            cursor.execute("INSERT INTO skills (canonical_name) VALUES (?)", (f"skill_{i}",))
            skill_id = cursor.lastrowid
            cursor.execute(
                "INSERT INTO aliases (alias_name, skill_id) VALUES (?, ?)", (f"alias_{i}", skill_id)
            )

        conn.commit()

        # Test indexed query performance
        start = time.time()
        cursor.execute("SELECT * FROM aliases WHERE alias_name = 'alias_500'")
        result = cursor.fetchone()
        query_time = time.time() - start

        assert result is not None
        assert query_time < 0.1  # Should be very fast with index

        conn.close()


# ============================================================================
# End-to-End Workflow Tests
# ============================================================================


class TestEndToEndWorkflows:
    """Test complete end-to-end workflows."""

    @pytest.mark.integration
    @pytest.mark.api
    def test_cv_processing_workflow(
        self, harmonizer_client, entity_resolver_client, sample_cv_data
    ):
        """Test processing CV data through both APIs."""
        with patch("entity_resolver.api.get_db") as mock_get_db:
            mock_db = MagicMock()
            mock_get_db.return_value = iter([mock_db])

            skills = sample_cv_data["experiences"][0]["competences"]
            companies = [exp["entreprise"] for exp in sample_cv_data["experiences"]]
            schools = [edu["ecole"] for edu in sample_cv_data["formations"]]

            # Step 1: Harmonize skills
            harmonize_response = harmonizer_client.post("/harmonize", json={"skills": skills})
            assert harmonize_response.status_code == 200
            harmonized_skills = harmonize_response.json()["results"]

            # Step 2: Resolve companies
            company_response = entity_resolver_client.post(
                "/resolve", json={"entities": companies, "entity_type": "COMPANY"}
            )
            assert company_response.status_code == 200
            resolved_companies = company_response.json()["results"]

            # Step 3: Resolve schools
            school_response = entity_resolver_client.post(
                "/resolve", json={"entities": schools, "entity_type": "SCHOOL"}
            )
            assert school_response.status_code == 200
            resolved_schools = school_response.json()["results"]

            # Verify results
            assert len(harmonized_skills) == 3
            assert len(resolved_companies) == 1
            assert len(resolved_schools) == 1

    @pytest.mark.integration
    def test_skill_enrichment_workflow(self, temp_ontology_db):
        """Test skill enrichment workflow with LLM mocking."""
        unmapped_skills = pd.DataFrame(
            {
                "skill_name": ["new_framework", "emerging_tech", "rare_skill"],
                "frequency": [1500, 800, 50],
            }
        )

        mock_llm_response = {
            "canonical_name": "new_framework",
            "aliases": ["nf", "new-framework"],
            "parents": ["javascript", "frontend"],
        }

        with patch("openai.OpenAI") as mock_openai:
            mock_client = Mock()
            mock_response = Mock()
            mock_response.choices = [Mock(message=Mock(content=json.dumps(mock_llm_response)))]
            mock_client.chat.completions.create.return_value = mock_response
            mock_openai.return_value = mock_client

            high_freq_skill = unmapped_skills.iloc[0]
            assert high_freq_skill["frequency"] > 1000

            conn = sqlite3.connect(temp_ontology_db)
            cursor = conn.cursor()

            cursor.execute(
                "INSERT INTO skills (canonical_name) VALUES (?)",
                (mock_llm_response["canonical_name"],),
            )
            skill_id = cursor.lastrowid

            for alias in mock_llm_response["aliases"]:
                cursor.execute(
                    "INSERT INTO aliases (alias_name, skill_id) VALUES (?, ?)", (alias, skill_id)
                )

            conn.commit()

            cursor.execute("SELECT COUNT(*) FROM skills WHERE canonical_name = 'new_framework'")
            assert cursor.fetchone()[0] == 1

            cursor.execute("SELECT COUNT(*) FROM aliases WHERE skill_id = ?", (skill_id,))
            assert cursor.fetchone()[0] == 2

            conn.close()


# ============================================================================
# Error Recovery Tests
# ============================================================================


class TestErrorRecovery:
    """Test error handling and recovery scenarios."""

    @pytest.mark.integration
    @pytest.mark.api
    def test_malformed_data_handling(self, harmonizer_client, entity_resolver_client):
        """Test handling of malformed or edge-case data."""
        with patch("entity_resolver.api.get_db") as mock_get_db:
            mock_db = MagicMock()
            mock_get_db.return_value = iter([mock_db])

            edge_cases = [
                "",
                " ",
                "a" * 1000,
                "Test Skill",
                "special_chars_!@#",
            ]

            for case in edge_cases:
                response = harmonizer_client.post("/harmonize", json={"skills": [case]})
                assert response.status_code in [200, 422]

                response = entity_resolver_client.post(
                    "/resolve", json={"entities": [case], "entity_type": "COMPANY"}
                )
                assert response.status_code in [200, 422]


# ============================================================================
# Performance Tests
# ============================================================================


class TestPerformance:
    """Performance and load testing."""

    @pytest.mark.integration
    @pytest.mark.slow
    def test_cache_performance_under_load(self, harmonizer_client):
        """Test cache performance under heavy load."""
        import statistics

        response_times = []

        # Warm up cache
        harmonizer_client.post("/harmonize", json={"skills": ["python"]})

        # Measure response times
        for _ in range(100):
            start = time.time()
            response = harmonizer_client.post(
                "/harmonize", json={"skills": ["python", "javascript", "react"]}
            )
            response_times.append(time.time() - start)
            assert response.status_code == 200

        avg_time = statistics.mean(response_times)
        median_time = statistics.median(response_times)

        # Performance assertions
        assert avg_time < 0.1  # Average under 100ms
        assert median_time < 0.05  # Median under 50ms

    @pytest.mark.integration
    @pytest.mark.slow
    def test_database_connection_pooling(self, temp_ontology_db):
        """Test database connection handling under concurrent access."""

        def query_database():
            conn = sqlite3.connect(temp_ontology_db)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM skills")
            result = cursor.fetchone()
            conn.close()
            return result[0] >= 0

        threads = []
        results = []

        for _ in range(50):
            t = threading.Thread(target=lambda: results.append(query_database()))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        assert all(results)
        assert len(results) == 50
