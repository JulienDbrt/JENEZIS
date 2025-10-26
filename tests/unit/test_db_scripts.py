#!/usr/bin/env python3
"""
Tests for database scripts (migrate_ontology_to_db and optimize_indexes).
"""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest


class TestMigrateOntology:
    """Test migrate_ontology_to_db script."""

    @pytest.mark.unit
    def test_migrate_function_exists(self):
        """Test that migrate function exists."""
        from src.db.migrate_ontology_to_db import migrate_to_database

        assert callable(migrate_to_database)

    @pytest.mark.unit
    def test_migrate_with_empty_data(self):
        """Test migration with empty data - should return early."""
        from src.db.migrate_ontology_to_db import migrate_to_database

        mock_conn = Mock()
        mock_cursor = Mock()
        mock_conn.cursor.return_value = mock_cursor

        with patch("sqlite3.connect", return_value=mock_conn):
            # With empty data, function returns early
            migrate_to_database({})

        # Should NOT execute anything with empty data
        assert not mock_cursor.execute.called

    @pytest.mark.unit
    def test_main_function_exists(self):
        """Test main function exists."""
        from src.db.migrate_ontology_to_db import main

        assert callable(main)

    @pytest.mark.unit
    def test_load_ontology_data(self):
        """Test loading ontology with actual data."""
        from src.db.migrate_ontology_to_db import migrate_to_database

        skill_hierarchy = {"python": {"aliases": ["py"], "parents": ["programming"]}}

        mock_conn = Mock()
        mock_cursor = Mock()
        mock_cursor.lastrowid = 1
        mock_cursor.fetchone.return_value = (1,)
        mock_conn.cursor.return_value = mock_cursor

        with patch("sqlite3.connect", return_value=mock_conn):
            # Pass skill hierarchy directly
            migrate_to_database(skill_hierarchy)

        mock_conn.commit.assert_called()


class TestOptimizeIndexes:
    """Test optimize_indexes script."""

    @pytest.mark.unit
    def test_optimize_function_exists(self):
        """Test that optimize function exists."""
        from src.db.optimize_indexes import optimize_database

        assert callable(optimize_database)

    @pytest.mark.unit
    def test_optimize_with_mock_db(self):
        """Test optimization with mock database."""
        from src.db.optimize_indexes import optimize_database

        mock_conn = Mock()
        mock_cursor = Mock()
        mock_conn.cursor.return_value = mock_cursor

        # Mock journal mode and other queries
        mock_cursor.fetchone.return_value = ("wal",)
        # Mock index queries
        mock_cursor.fetchall.return_value = [
            ("idx_test", "test_table", "CREATE INDEX idx_test ON test_table(col)")
        ]

        mock_path = Mock(spec=Path)
        mock_path.exists.return_value = True
        mock_path.name = "test.db"

        with patch("sqlite3.connect", return_value=mock_conn):
            optimize_database(mock_path, [])

        # Should have executed some optimization queries
        assert mock_cursor.execute.called

    @pytest.mark.unit
    def test_main_function_exists(self):
        """Test main function exists."""
        from src.db.optimize_indexes import main

        assert callable(main)

    @pytest.mark.unit
    def test_create_indexes(self):
        """Test creating new indexes."""
        from src.db.optimize_indexes import optimize_database

        optimizations = [
            "CREATE INDEX idx_skills ON skills(canonical_name)",
            "CREATE INDEX idx_aliases ON aliases(alias_name)",
        ]

        mock_conn = Mock()
        mock_cursor = Mock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = ("wal",)
        mock_cursor.fetchall.return_value = []  # No existing indexes

        mock_path = Mock(spec=Path)
        mock_path.exists.return_value = True
        mock_path.name = "test.db"

        with patch("sqlite3.connect", return_value=mock_conn):
            optimize_database(mock_path, optimizations)

        # Should create indexes
        create_index_calls = [
            call for call in mock_cursor.execute.call_args_list if "CREATE INDEX" in str(call)
        ]
        assert len(create_index_calls) >= 2

    @pytest.mark.unit
    def test_vacuum_and_analyze(self):
        """Test VACUUM and ANALYZE operations."""
        from src.db.optimize_indexes import optimize_database

        mock_conn = Mock()
        mock_cursor = Mock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = ("wal",)
        mock_cursor.fetchall.return_value = []

        mock_path = Mock(spec=Path)
        mock_path.exists.return_value = True
        mock_path.name = "test.db"

        with patch("sqlite3.connect", return_value=mock_conn):
            optimize_database(mock_path, [])

        # Should run some database commands
        assert mock_cursor.execute.called
