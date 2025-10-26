#!/usr/bin/env python3
"""
Integration tests for both Harmonizer and Entity Resolver APIs.
Tests cross-API interactions, database operations, and end-to-end workflows.
"""

import json
import sqlite3
from unittest.mock import Mock, patch

import pandas as pd
import pytest


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

        # Verify hierarchy by checking stats
        stats_response = harmonizer_client.get("/stats")
        assert stats_response.json()["total_relations"] > 0

    @pytest.mark.integration
    @pytest.mark.api
    def test_entity_resolver_enrichment_workflow(self, entity_resolver_client, temp_entity_db):
        """Test complete enrichment workflow from unknown entity to queue."""
        # Step 1: Resolve unknown entities
        response = entity_resolver_client.post(
            "/resolve",
            json={
                "entities": ["NewTechCorp", "StartupXYZ", "InnovateCo"],
                "entity_type": "COMPANY",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["stats"]["unknown"] == 3
        assert data["stats"]["queued_for_enrichment"] == 3

        # Step 2: Check enrichment queue
        queue_response = entity_resolver_client.get("/enrichment/queue")
        assert queue_response.status_code == 200
        queue_data = queue_response.json()

        assert queue_data["count"] == 3
        queued_ids = [item["canonical_id"] for item in queue_data["queue"]]
        assert "newtechcorp" in queued_ids
        assert "startupxyz" in queued_ids
        assert "innovateco" in queued_ids

        # Step 3: Simulate enrichment processing
        conn = sqlite3.connect(temp_entity_db)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE enrichment_queue SET status = 'COMPLETED' WHERE canonical_id = 'newtechcorp'"
        )
        conn.commit()
        conn.close()

        # Step 4: Check queue again
        queue_response = entity_resolver_client.get("/enrichment/queue")
        queue_data = queue_response.json()

        # Should still show all 3 (limit is 50)
        completed = [item for item in queue_data["queue"] if item["status"] == "COMPLETED"]
        assert len(completed) == 1

    @pytest.mark.integration
    @pytest.mark.api
    def test_concurrent_cache_updates(self, harmonizer_client, temp_ontology_db, auth_headers):
        """Test that cache updates don't cause race conditions."""
        import threading
        import time

        results = []

        def harmonize_skills():
            response = harmonizer_client.post(
                "/harmonize", json={"skills": ["python", "javascript"]}
            )
            results.append(response.status_code == 200)

        def reload_cache():
            time.sleep(0.01)  # Small delay
            response = harmonizer_client.post("/admin/reload", headers=auth_headers)
            results.append(response.status_code == 200)

        # Start threads
        threads = []
        for _ in range(5):
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


class TestDatabaseOperations:
    """Test database operations and consistency."""

    @pytest.mark.integration
    def test_database_transaction_rollback(self, temp_ontology_db):
        """Test that database transactions rollback on error."""
        conn = sqlite3.connect(temp_ontology_db)
        cursor = conn.cursor()

        # Enable foreign key constraints
        cursor.execute("PRAGMA foreign_keys = ON")

        try:
            cursor.execute("BEGIN")
            cursor.execute("INSERT INTO skills (canonical_name) VALUES ('test_skill')")
            # This establishes a valid skill before attempting to create an invalid alias

            # This should fail due to foreign key constraint
            cursor.execute("INSERT INTO aliases (alias_name, skill_id) VALUES ('test', 99999)")
            cursor.execute("COMMIT")
        except sqlite3.IntegrityError:
            cursor.execute("ROLLBACK")

        # Check that nothing was inserted
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
        import time

        start = time.time()
        cursor.execute("SELECT * FROM aliases WHERE alias_name = 'alias_500'")
        result = cursor.fetchone()
        query_time = time.time() - start

        assert result is not None
        assert query_time < 0.01  # Should be very fast with index

        conn.close()


class TestEndToEndWorkflows:
    """Test complete end-to-end workflows."""

    @pytest.mark.integration
    @pytest.mark.api
    def test_cv_processing_workflow(
        self, harmonizer_client, entity_resolver_client, sample_cv_data
    ):
        """Test processing CV data through both APIs."""
        # Extract data from CV
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
        assert all(skill["is_known"] for skill in harmonized_skills)

        assert len(resolved_companies) == 1
        assert resolved_companies[0]["canonical_id"] == "google"

        assert len(resolved_schools) == 1
        assert resolved_schools[0]["canonical_id"] == "mit"

    @pytest.mark.integration
    def test_skill_enrichment_workflow(self, temp_ontology_db):
        """Test skill enrichment workflow with LLM mocking."""
        # Simulate unmapped skills analysis
        unmapped_skills = pd.DataFrame(
            {
                "skill_name": ["new_framework", "emerging_tech", "rare_skill"],
                "frequency": [1500, 800, 50],
            }
        )

        # Mock LLM response for enrichment
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

            # Process high-frequency skill (would be auto-approved)
            high_freq_skill = unmapped_skills.iloc[0]
            assert high_freq_skill["frequency"] > 1000

            # In real workflow, this would insert to database
            conn = sqlite3.connect(temp_ontology_db)
            cursor = conn.cursor()

            # Insert the new skill
            cursor.execute(
                "INSERT INTO skills (canonical_name) VALUES (?)",
                (mock_llm_response["canonical_name"],),
            )
            skill_id = cursor.lastrowid

            # Insert aliases
            for alias in mock_llm_response["aliases"]:
                cursor.execute(
                    "INSERT INTO aliases (alias_name, skill_id) VALUES (?, ?)", (alias, skill_id)
                )

            conn.commit()

            # Verify insertion
            cursor.execute("SELECT COUNT(*) FROM skills WHERE canonical_name = 'new_framework'")
            assert cursor.fetchone()[0] == 1

            cursor.execute("SELECT COUNT(*) FROM aliases WHERE skill_id = ?", (skill_id,))
            assert cursor.fetchone()[0] == 2

            conn.close()

    @pytest.mark.integration
    @pytest.mark.api
    def test_cross_api_data_consistency(
        self,
        harmonizer_client,
        entity_resolver_client,
        temp_ontology_db,
        temp_entity_db,
        auth_headers,
    ):
        """Test data consistency across both APIs."""
        # Get initial stats from both APIs
        harm_stats = harmonizer_client.get("/stats").json()
        entity_stats = entity_resolver_client.get("/stats").json()

        initial_skills = harm_stats["total_skills"]
        initial_entities = sum(entity_stats["entities"].values())

        # Add data through admin endpoints
        harmonizer_client.post("/admin/reload", headers=auth_headers)
        entity_resolver_client.post("/admin/reload", headers=auth_headers)

        # Stats should remain consistent
        new_harm_stats = harmonizer_client.get("/stats").json()
        new_entity_stats = entity_resolver_client.get("/stats").json()

        assert new_harm_stats["total_skills"] == initial_skills
        assert sum(new_entity_stats["entities"].values()) == initial_entities


class TestErrorRecovery:
    """Test error handling and recovery scenarios."""

    @pytest.mark.integration
    @pytest.mark.api
    def test_api_recovery_after_db_corruption(
        self, harmonizer_client, temp_ontology_db, auth_headers
    ):
        """Test API recovery after database issues."""
        # Corrupt the database by deleting a table
        conn = sqlite3.connect(temp_ontology_db)
        cursor = conn.cursor()
        cursor.execute("DROP TABLE hierarchy")
        conn.commit()
        conn.close()

        # API should handle gracefully
        response = harmonizer_client.post("/admin/reload", headers=auth_headers)
        # Should complete even with missing table
        assert response.status_code == 200

        # Basic functionality should still work
        response = harmonizer_client.post("/harmonize", json={"skills": ["test"]})
        assert response.status_code == 200

    @pytest.mark.integration
    @pytest.mark.api
    def test_malformed_data_handling(self, harmonizer_client, entity_resolver_client):
        """Test handling of malformed or edge-case data."""
        # Test with various edge cases
        edge_cases = [
            None,
            "",
            " ",
            "a" * 1000,  # Very long string
            "🚀 Emoji Skills 🎯",
            "<script>alert('xss')</script>",
            "'; DROP TABLE skills; --",
        ]

        for case in edge_cases:
            if case is None:
                continue

            # Test harmonizer
            response = harmonizer_client.post("/harmonize", json={"skills": [case]})
            assert response.status_code in [200, 422]

            # Test entity resolver
            response = entity_resolver_client.post(
                "/resolve", json={"entities": [case], "entity_type": "COMPANY"}
            )
            assert response.status_code in [200, 422]


class TestPerformance:
    """Performance and load testing."""

    @pytest.mark.integration
    @pytest.mark.slow
    def test_cache_performance_under_load(self, harmonizer_client):
        """Test cache performance under heavy load."""
        import statistics
        import time

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

        # Calculate statistics
        avg_time = statistics.mean(response_times)
        median_time = statistics.median(response_times)
        p95_time = statistics.quantiles(response_times, n=20)[18]  # 95th percentile

        # Performance assertions
        assert avg_time < 0.05  # Average under 50ms
        assert median_time < 0.03  # Median under 30ms
        assert p95_time < 0.1  # 95% under 100ms

    @pytest.mark.integration
    @pytest.mark.slow
    def test_database_connection_pooling(self, temp_ontology_db):
        """Test database connection handling under concurrent access."""
        import sqlite3
        import threading

        def query_database():
            conn = sqlite3.connect(temp_ontology_db)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM skills")
            result = cursor.fetchone()
            conn.close()
            return result[0] > 0

        # Run many concurrent queries
        threads = []
        results = []

        for _ in range(50):
            t = threading.Thread(target=lambda: results.append(query_database()))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # All queries should succeed
        assert all(results)
        assert len(results) == 50
