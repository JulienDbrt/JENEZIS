#!/usr/bin/env python3
"""
Tests for database scripts (migrate_ontology_to_db).
"""

import sqlite3
import tempfile
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

        # With empty data, function should return early without any errors
        migrate_to_database({})

    @pytest.mark.unit
    def test_main_function_exists(self):
        """Test main function exists."""
        from src.db.migrate_ontology_to_db import main

        assert callable(main)

    @pytest.mark.unit
    def test_load_skill_hierarchy_empty_file(self):
        """Test load_skill_hierarchy with no file."""
        from src.db.migrate_ontology_to_db import load_skill_hierarchy

        result = load_skill_hierarchy(None)
        assert result == {}

    @pytest.mark.unit
    def test_load_skill_hierarchy_nonexistent_file(self):
        """Test load_skill_hierarchy with nonexistent file."""
        from src.db.migrate_ontology_to_db import load_skill_hierarchy

        result = load_skill_hierarchy("/nonexistent/path.json")
        assert result == {}

    @pytest.mark.unit
    def test_migrate_with_skill_data(self):
        """Test migration with actual skill data using mocks."""
        from src.db.migrate_ontology_to_db import migrate_to_database

        skill_hierarchy = {
            "python": {"aliases": ["py", "python3"], "parents": ["programming"]},
            "javascript": {"aliases": ["js"], "parents": ["programming"]},
        }

        mock_conn = Mock()
        mock_cursor = Mock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = (1,)  # Return skill ID

        with patch("src.db.migrate_ontology_to_db.sqlite3.connect", return_value=mock_conn):
            migrate_to_database(skill_hierarchy)

        # Verify commit was called
        mock_conn.commit.assert_called()

        # Verify execute was called multiple times for skills, aliases, hierarchy
        assert mock_cursor.execute.call_count > 5
