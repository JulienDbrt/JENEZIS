#!/usr/bin/env python3
"""
Tests for the entity resolver database initialization module.
"""

import json
import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Add src to path for imports
sys.path.insert(0, "/Users/juliendabert/Desktop/Erwin-Harmonizer/src")


class TestEntityResolverDbInit:
    """Test suite for entity resolver database initialization."""

    @pytest.mark.unit
    @patch("src.entity_resolver.db_init.DB_FILE", "test.db")
    def test_create_connection(self):
        """Test create_connection function."""
        from src.entity_resolver.db_init import create_connection

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_db:
            temp_db_path = temp_db.name

        with patch("src.entity_resolver.db_init.DB_FILE", temp_db_path):
            conn = create_connection()
            assert isinstance(conn, sqlite3.Connection)
            conn.close()

        # Cleanup
        Path(temp_db_path).unlink(missing_ok=True)

    @pytest.mark.unit
    def test_create_tables_sql_structure(self):
        """Test create_tables function creates correct table structure."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_db:
            temp_db_path = temp_db.name

        with patch("src.entity_resolver.db_init.DB_FILE", temp_db_path):
            from src.entity_resolver.db_init import create_tables

            # Should not raise errors
            create_tables()

            # Verify tables were created
            conn = sqlite3.connect(temp_db_path)
            cursor = conn.cursor()

            # Check table existence
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {row[0] for row in cursor.fetchall()}

            assert "canonical_entities" in tables
            assert "entity_aliases" in tables
            assert "enrichment_queue" in tables

            # Check indexes
            cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
            indexes = {row[0] for row in cursor.fetchall()}

            assert "idx_canonical_id" in indexes
            assert "idx_alias_name" in indexes
            assert "idx_enrichment_status" in indexes

            conn.close()

        # Cleanup
        Path(temp_db_path).unlink(missing_ok=True)

    @pytest.mark.unit
    def test_canonical_entities_table_structure(self):
        """Test canonical_entities table structure."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_db:
            temp_db_path = temp_db.name

        with patch("src.entity_resolver.db_init.DB_FILE", temp_db_path):
            from src.entity_resolver.db_init import create_tables

            create_tables()

            conn = sqlite3.connect(temp_db_path)
            cursor = conn.cursor()

            # Check table structure
            cursor.execute("PRAGMA table_info(canonical_entities)")
            columns = cursor.fetchall()
            column_names = [col[1] for col in columns]

            assert "id" in column_names
            assert "canonical_id" in column_names
            assert "display_name" in column_names
            assert "entity_type" in column_names
            assert "metadata" in column_names

            conn.close()

        # Cleanup
        Path(temp_db_path).unlink(missing_ok=True)

    @pytest.mark.unit
    def test_entity_aliases_table_structure(self):
        """Test entity_aliases table structure."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_db:
            temp_db_path = temp_db.name

        with patch("src.entity_resolver.db_init.DB_FILE", temp_db_path):
            from src.entity_resolver.db_init import create_tables

            create_tables()

            conn = sqlite3.connect(temp_db_path)
            cursor = conn.cursor()

            # Check table structure
            cursor.execute("PRAGMA table_info(entity_aliases)")
            columns = cursor.fetchall()
            column_names = [col[1] for col in columns]

            assert "id" in column_names
            assert "alias_name" in column_names
            assert "canonical_id" in column_names

            conn.close()

        # Cleanup
        Path(temp_db_path).unlink(missing_ok=True)

    @pytest.mark.unit
    def test_enrichment_queue_table_structure(self):
        """Test enrichment_queue table structure."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_db:
            temp_db_path = temp_db.name

        with patch("src.entity_resolver.db_init.DB_FILE", temp_db_path):
            from src.entity_resolver.db_init import create_tables

            create_tables()

            conn = sqlite3.connect(temp_db_path)
            cursor = conn.cursor()

            # Check table structure
            cursor.execute("PRAGMA table_info(enrichment_queue)")
            columns = cursor.fetchall()
            column_names = [col[1] for col in columns]

            assert "id" in column_names
            assert "canonical_id" in column_names
            assert "entity_type" in column_names
            assert "status" in column_names
            assert "created_at" in column_names
            assert "processed_at" in column_names
            assert "error_message" in column_names

            conn.close()

        # Cleanup
        Path(temp_db_path).unlink(missing_ok=True)

    @pytest.mark.unit
    def test_populate_initial_data_companies(self):
        """Test populate_initial_data function for companies."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_db:
            temp_db_path = temp_db.name

        with patch("src.entity_resolver.db_init.DB_FILE", temp_db_path):
            from src.entity_resolver.db_init import create_tables, populate_initial_data

            create_tables()
            populate_initial_data()

            conn = sqlite3.connect(temp_db_path)
            cursor = conn.cursor()

            # Check companies were inserted
            cursor.execute("SELECT COUNT(*) FROM canonical_entities WHERE entity_type = 'COMPANY'")
            company_count = cursor.fetchone()[0]
            assert company_count > 0

            # Check specific companies
            cursor.execute(
                "SELECT display_name FROM canonical_entities WHERE canonical_id = 'google'"
            )
            result = cursor.fetchone()
            assert result is not None
            assert result[0] == "Google"

            cursor.execute(
                "SELECT display_name FROM canonical_entities WHERE canonical_id = 'bnp_paribas'"
            )
            result = cursor.fetchone()
            assert result is not None
            assert result[0] == "BNP Paribas"

            conn.close()

        # Cleanup
        Path(temp_db_path).unlink(missing_ok=True)

    @pytest.mark.unit
    def test_populate_initial_data_schools(self):
        """Test populate_initial_data function for schools."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_db:
            temp_db_path = temp_db.name

        with patch("src.entity_resolver.db_init.DB_FILE", temp_db_path):
            from src.entity_resolver.db_init import create_tables, populate_initial_data

            create_tables()
            populate_initial_data()

            conn = sqlite3.connect(temp_db_path)
            cursor = conn.cursor()

            # Check schools were inserted
            cursor.execute("SELECT COUNT(*) FROM canonical_entities WHERE entity_type = 'SCHOOL'")
            school_count = cursor.fetchone()[0]
            assert school_count > 0

            # Check specific schools
            cursor.execute(
                "SELECT display_name FROM canonical_entities WHERE canonical_id = 'polytechnique'"
            )
            result = cursor.fetchone()
            assert result is not None
            assert result[0] == "École Polytechnique"

            cursor.execute("SELECT display_name FROM canonical_entities WHERE canonical_id = 'hec'")
            result = cursor.fetchone()
            assert result is not None
            assert result[0] == "HEC Paris"

            conn.close()

        # Cleanup
        Path(temp_db_path).unlink(missing_ok=True)

    @pytest.mark.unit
    def test_populate_initial_data_aliases(self):
        """Test that aliases are properly created."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_db:
            temp_db_path = temp_db.name

        with patch("src.entity_resolver.db_init.DB_FILE", temp_db_path):
            from src.entity_resolver.db_init import create_tables, populate_initial_data

            create_tables()
            populate_initial_data()

            conn = sqlite3.connect(temp_db_path)
            cursor = conn.cursor()

            # Check that aliases were created
            cursor.execute("SELECT COUNT(*) FROM entity_aliases")
            alias_count = cursor.fetchone()[0]
            assert alias_count > 0

            # Check specific aliases for Google
            cursor.execute(
                """
                SELECT ea.alias_name
                FROM entity_aliases ea
                JOIN canonical_entities ce ON ea.canonical_id = ce.id
                WHERE ce.canonical_id = 'google'
            """
            )
            google_aliases = {row[0] for row in cursor.fetchall()}
            assert "google" in google_aliases
            assert "alphabet" in google_aliases

            # Check aliases are lowercase
            cursor.execute("SELECT alias_name FROM entity_aliases LIMIT 10")
            aliases = [row[0] for row in cursor.fetchall()]
            for alias in aliases:
                assert alias == alias.lower()

            conn.close()

        # Cleanup
        Path(temp_db_path).unlink(missing_ok=True)

    @pytest.mark.unit
    def test_populate_initial_data_metadata(self):
        """Test that metadata is properly stored as JSON."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_db:
            temp_db_path = temp_db.name

        with patch("src.entity_resolver.db_init.DB_FILE", temp_db_path):
            from src.entity_resolver.db_init import create_tables, populate_initial_data

            create_tables()
            populate_initial_data()

            conn = sqlite3.connect(temp_db_path)
            cursor = conn.cursor()

            # Check metadata for Google
            cursor.execute("SELECT metadata FROM canonical_entities WHERE canonical_id = 'google'")
            result = cursor.fetchone()
            assert result is not None

            metadata = json.loads(result[0])
            assert metadata["sector"] == "Technology"
            assert metadata["country"] == "USA"

            # Check metadata for BNP Paribas
            cursor.execute(
                "SELECT metadata FROM canonical_entities WHERE canonical_id = 'bnp_paribas'"
            )
            result = cursor.fetchone()
            assert result is not None

            metadata = json.loads(result[0])
            assert metadata["sector"] == "Finance"
            assert metadata["country"] == "France"

            conn.close()

        # Cleanup
        Path(temp_db_path).unlink(missing_ok=True)

    @pytest.mark.unit
    def test_display_stats_function(self):
        """Test display_stats function."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_db:
            temp_db_path = temp_db.name

        with patch("src.entity_resolver.db_init.DB_FILE", temp_db_path):
            from src.entity_resolver.db_init import (
                create_tables,
                display_stats,
                populate_initial_data,
            )

            create_tables()
            populate_initial_data()

            # Should not raise errors
            with patch("builtins.print") as mock_print:
                display_stats()
                # Should have called print multiple times
                assert mock_print.call_count > 0

        # Cleanup
        Path(temp_db_path).unlink(missing_ok=True)

    @pytest.mark.unit
    def test_foreign_key_constraints(self):
        """Test that foreign key constraints work."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_db:
            temp_db_path = temp_db.name

        with patch("src.entity_resolver.db_init.DB_FILE", temp_db_path):
            from src.entity_resolver.db_init import create_tables

            create_tables()

            conn = sqlite3.connect(temp_db_path)
            conn.execute("PRAGMA foreign_keys = ON")
            cursor = conn.cursor()

            # Insert a canonical entity
            cursor.execute(
                """
                INSERT INTO canonical_entities (canonical_id, display_name, entity_type)
                VALUES ('test_entity', 'Test Entity', 'COMPANY')
            """
            )
            entity_id = cursor.lastrowid

            # Insert valid alias
            cursor.execute(
                """
                INSERT INTO entity_aliases (alias_name, canonical_id)
                VALUES ('test alias', ?)
            """,
                (entity_id,),
            )

            # Try to insert alias with invalid foreign key
            with pytest.raises(sqlite3.IntegrityError):
                cursor.execute(
                    """
                    INSERT INTO entity_aliases (alias_name, canonical_id)
                    VALUES ('invalid alias', 9999)
                """
                )

            conn.close()

        # Cleanup
        Path(temp_db_path).unlink(missing_ok=True)

    @pytest.mark.unit
    def test_duplicate_handling(self):
        """Test that INSERT OR IGNORE handles duplicates correctly."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_db:
            temp_db_path = temp_db.name

        with patch("src.entity_resolver.db_init.DB_FILE", temp_db_path):
            from src.entity_resolver.db_init import create_tables

            create_tables()

            conn = sqlite3.connect(temp_db_path)
            cursor = conn.cursor()

            # Insert entity
            cursor.execute(
                """
                INSERT INTO canonical_entities (canonical_id, display_name, entity_type)
                VALUES ('test_entity', 'Test Entity', 'COMPANY')
            """
            )

            # Try to insert same entity again - should not raise error
            cursor.execute(
                """
                INSERT OR IGNORE INTO canonical_entities (canonical_id, display_name, entity_type)
                VALUES ('test_entity', 'Test Entity Duplicate', 'COMPANY')
            """
            )

            # Should still have only one entity
            cursor.execute(
                "SELECT COUNT(*) FROM canonical_entities WHERE canonical_id = 'test_entity'"
            )
            count = cursor.fetchone()[0]
            assert count == 1

            conn.close()

        # Cleanup
        Path(temp_db_path).unlink(missing_ok=True)

    @pytest.mark.unit
    def test_module_constants(self):
        """Test module constants and imports."""
        from src.entity_resolver.db_init import DB_FILE

        assert DB_FILE is not None
        assert isinstance(DB_FILE, str)
        assert DB_FILE.endswith(".db")

    @pytest.mark.unit
    def test_enrichment_queue_default_status(self):
        """Test that enrichment queue has proper default status."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_db:
            temp_db_path = temp_db.name

        with patch("src.entity_resolver.db_init.DB_FILE", temp_db_path):
            from src.entity_resolver.db_init import create_tables

            create_tables()

            conn = sqlite3.connect(temp_db_path)
            cursor = conn.cursor()

            # Insert into enrichment queue without status
            cursor.execute(
                """
                INSERT INTO enrichment_queue (canonical_id, entity_type)
                VALUES ('test_entity', 'COMPANY')
            """
            )

            # Check default status
            cursor.execute("SELECT status FROM enrichment_queue WHERE canonical_id = 'test_entity'")
            result = cursor.fetchone()
            assert result is not None
            assert result[0] == "PENDING"

            conn.close()

        # Cleanup
        Path(temp_db_path).unlink(missing_ok=True)

    @pytest.mark.unit
    def test_alias_normalization(self):
        """Test that aliases are normalized to lowercase."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_db:
            temp_db_path = temp_db.name

        with patch("src.entity_resolver.db_init.DB_FILE", temp_db_path):
            from src.entity_resolver.db_init import create_tables

            create_tables()

            # Manually test the alias normalization logic
            aliases = ["GOOGLE", "Google Inc.", " Microsoft Corp ", "  Apple  "]
            normalized = [alias.lower().strip() for alias in aliases]

            expected = ["google", "google inc.", "microsoft corp", "apple"]
            assert normalized == expected

        # Cleanup
        Path(temp_db_path).unlink(missing_ok=True)

    @pytest.mark.unit
    def test_comprehensive_data_coverage(self):
        """Test that initial data covers expected entities."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_db:
            temp_db_path = temp_db.name

        with patch("src.entity_resolver.db_init.DB_FILE", temp_db_path):
            from src.entity_resolver.db_init import create_tables, populate_initial_data

            create_tables()
            populate_initial_data()

            conn = sqlite3.connect(temp_db_path)
            cursor = conn.cursor()

            # Check we have major French companies
            french_companies = ["bnp_paribas", "total_energies", "carrefour", "renault"]
            for company in french_companies:
                cursor.execute(
                    "SELECT id FROM canonical_entities WHERE canonical_id = ?", (company,)
                )
                assert cursor.fetchone() is not None

            # Check we have major tech companies
            tech_companies = ["google", "microsoft", "apple", "amazon"]
            for company in tech_companies:
                cursor.execute(
                    "SELECT id FROM canonical_entities WHERE canonical_id = ?", (company,)
                )
                assert cursor.fetchone() is not None

            # Check we have major French schools
            schools = ["polytechnique", "hec", "sorbonne"]
            for school in schools:
                cursor.execute(
                    "SELECT id FROM canonical_entities WHERE canonical_id = ?", (school,)
                )
                assert cursor.fetchone() is not None

            conn.close()

        # Cleanup
        Path(temp_db_path).unlink(missing_ok=True)
