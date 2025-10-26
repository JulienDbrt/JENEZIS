"""Tests for the entity enrichment workflow with NEEDS_REVIEW status."""

import csv
import json
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest


class TestEnrichmentWorkflow:
    """Test the complete enrichment workflow including NEEDS_REVIEW status."""

    @pytest.fixture
    def temp_db(self):
        """Create a temporary database for testing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Create enrichment queue table
        cursor.execute(
            """
            CREATE TABLE enrichment_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                canonical_id TEXT UNIQUE NOT NULL,
                entity_type TEXT NOT NULL,
                status TEXT DEFAULT 'PENDING',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                processed_at TIMESTAMP,
                error_message TEXT
            )
        """
        )

        # Create canonical_entities table
        cursor.execute(
            """
            CREATE TABLE canonical_entities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                canonical_id TEXT UNIQUE NOT NULL,
                display_name TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                metadata TEXT
            )
        """
        )

        # Add test data
        cursor.execute(
            """
            INSERT INTO canonical_entities (canonical_id, display_name, entity_type, metadata)
            VALUES
            ('test_company', 'Test Company', 'COMPANY', '{}'),
            ('unknown_company', 'Unknown Company', 'COMPANY', '{}')
        """
        )

        cursor.execute(
            """
            INSERT INTO enrichment_queue (canonical_id, entity_type, status)
            VALUES
            ('test_company', 'COMPANY', 'PENDING'),
            ('unknown_company', 'COMPANY', 'PENDING')
        """
        )

        conn.commit()
        conn.close()

        yield db_path

        # Cleanup
        Path(db_path).unlink(missing_ok=True)

    @patch("src.enrichment.wikipedia_enricher.requests.get")
    def test_enrichment_marks_needs_review_when_not_found(self, mock_get, temp_db):
        """Test that entities not found on Wikipedia are marked as NEEDS_REVIEW."""
        from src.enrichment import wikipedia_enricher

        # Mock Wikipedia API responses
        mock_response = Mock()
        mock_response.json.return_value = {"query": {"search": []}}  # No results
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        # Monkey-patch the DB file path
        original_db = wikipedia_enricher.RESOLVER_DB_FILE
        wikipedia_enricher.RESOLVER_DB_FILE = temp_db

        try:
            # Run enrichment in simulation mode
            wikipedia_enricher.main(use_neo4j=False)

            # Check the status was updated to NEEDS_REVIEW
            conn = sqlite3.connect(temp_db)
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT canonical_id, status, error_message
                FROM enrichment_queue
                WHERE status = 'NEEDS_REVIEW'
            """
            )
            results = cursor.fetchall()
            conn.close()

            assert len(results) == 2
            for row in results:
                assert row[1] == "NEEDS_REVIEW"
                assert "No Wikipedia data found" in row[2]
        finally:
            wikipedia_enricher.RESOLVER_DB_FILE = original_db

    def test_export_entity_review(self, temp_db):
        """Test exporting entities for human review."""
        from src.cli import export_entity_review

        # Update one entity to NEEDS_REVIEW
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE enrichment_queue
            SET status = 'NEEDS_REVIEW',
                error_message = 'No Wikipedia data found'
            WHERE canonical_id = 'unknown_company'
        """
        )
        conn.commit()
        conn.close()

        # Monkey-patch the DB path
        original_db = export_entity_review.RESOLVER_DB
        export_entity_review.RESOLVER_DB = Path(temp_db)

        with tempfile.TemporaryDirectory() as temp_dir:
            export_entity_review.OUTPUT_DIR = Path(temp_dir)

            try:
                # Run export
                export_entity_review.export_entities_for_review()

                # Check output file was created
                csv_files = list(Path(temp_dir).glob("entity_review_*.csv"))
                assert len(csv_files) > 0

                # Check content
                with open(csv_files[0], encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    rows = list(reader)

                assert len(rows) == 1
                assert rows[0]["canonical_id"] == "unknown_company"
                assert rows[0]["entity_type"] == "COMPANY"
                assert rows[0]["display_name"] == "Unknown Company"
            finally:
                export_entity_review.RESOLVER_DB = original_db

    def test_import_entity_enrichment(self, temp_db):
        """Test importing manually reviewed entity enrichments."""
        from src.cli import import_entity_enrichment

        # Create a CSV with approved enrichment
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            csv_path = f.name
            writer = csv.writer(f)
            writer.writerow(
                [
                    "canonical_id",
                    "display_name",
                    "entity_type",
                    "wikipedia_url",
                    "description",
                    "approve",
                    "notes",
                ]
            )
            writer.writerow(
                [
                    "unknown_company",
                    "Unknown Company",
                    "COMPANY",
                    "https://en.wikipedia.org/wiki/Test",
                    "Test description",
                    "OUI",
                    "Manually verified",
                ]
            )

        # Update entity to NEEDS_REVIEW status
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE enrichment_queue
            SET status = 'NEEDS_REVIEW'
            WHERE canonical_id = 'unknown_company'
        """
        )
        conn.commit()
        conn.close()

        # Monkey-patch the DB path
        original_db = import_entity_enrichment.RESOLVER_DB
        import_entity_enrichment.RESOLVER_DB = Path(temp_db)

        try:
            # Run import
            import_entity_enrichment.import_reviewed_entities(csv_path)

            # Check the entity was updated
            conn = sqlite3.connect(temp_db)
            cursor = conn.cursor()

            # Check enrichment queue status
            cursor.execute(
                """
                SELECT status, error_message
                FROM enrichment_queue
                WHERE canonical_id = 'unknown_company'
            """
            )
            queue_result = cursor.fetchone()
            assert queue_result[0] == "COMPLETED"
            assert "Manually reviewed" in queue_result[1]

            # Check metadata was updated
            cursor.execute(
                """
                SELECT metadata
                FROM canonical_entities
                WHERE canonical_id = 'unknown_company'
            """
            )
            metadata_result = cursor.fetchone()
            metadata = json.loads(metadata_result[0])
            assert metadata.get("wikipedia_url") == "https://en.wikipedia.org/wiki/Test"
            assert metadata.get("description") == "Test description"
            assert metadata.get("manually_reviewed") is True

            conn.close()
        finally:
            import_entity_enrichment.RESOLVER_DB = original_db
            Path(csv_path).unlink(missing_ok=True)

    @patch("src.enrichment.wikipedia_enricher.requests.get")
    def test_enrichment_completes_when_found(self, mock_get, temp_db):
        """Test that entities found on Wikipedia are marked as COMPLETED."""
        from src.enrichment import wikipedia_enricher

        # Mock successful Wikipedia API response
        mock_response = Mock()
        mock_response.json.side_effect = [
            # First call: search results
            {"query": {"search": [{"title": "Test Company", "snippet": "Test snippet"}]}},
            # Second call: page extract
            {
                "query": {
                    "pages": {
                        "123": {
                            "extract": "Test Company is a technology company.",
                            "categories": [{"title": "Category:Technology companies"}],
                        }
                    }
                }
            },
        ]
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        # Monkey-patch the DB file path
        original_db = wikipedia_enricher.RESOLVER_DB_FILE
        wikipedia_enricher.RESOLVER_DB_FILE = temp_db

        try:
            # Run enrichment in simulation mode
            wikipedia_enricher.main(use_neo4j=False)

            # Check at least one was marked as COMPLETED
            conn = sqlite3.connect(temp_db)
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT COUNT(*)
                FROM enrichment_queue
                WHERE status = 'COMPLETED'
            """
            )
            count = cursor.fetchone()[0]
            conn.close()

            assert count >= 1  # At least one should be completed
        finally:
            wikipedia_enricher.RESOLVER_DB_FILE = original_db

    def test_enrichment_queue_statistics(self, temp_db):
        """Test that enrichment queue statistics include NEEDS_REVIEW."""
        # Update statuses for testing
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE enrichment_queue
            SET status = 'NEEDS_REVIEW'
            WHERE canonical_id = 'unknown_company'
        """
        )
        cursor.execute(
            """
            UPDATE enrichment_queue
            SET status = 'COMPLETED'
            WHERE canonical_id = 'test_company'
        """
        )
        conn.commit()

        # Get statistics
        cursor.execute(
            """
            SELECT status, COUNT(*)
            FROM enrichment_queue
            GROUP BY status
        """
        )
        stats = dict(cursor.fetchall())
        conn.close()

        assert stats.get("NEEDS_REVIEW") == 1
        assert stats.get("COMPLETED") == 1
        assert "FAILED" not in stats or stats["FAILED"] == 0
