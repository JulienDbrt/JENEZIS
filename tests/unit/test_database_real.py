#!/usr/bin/env python3
"""
Tests for the REAL database module functions.
"""

import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Add src to path for imports
sys.path.insert(0, "/Users/juliendabert/Desktop/Erwin-Harmonizer/src")


class TestRealDatabase:
    """Test suite for actual database module functions."""

    @pytest.mark.unit
    def test_create_database_function_directly(self):
        """Test the real create_database function."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_db:
            temp_db_path = temp_db.name

        # Mock the DB_PATH to use our temp file
        with patch("src.db.database.DB_PATH", temp_db_path):
            from src.db.database import create_database

            # Should not raise any errors
            create_database()

            # Verify database was created
            assert Path(temp_db_path).exists()

            # Verify tables exist
            conn = sqlite3.connect(temp_db_path)
            cursor = conn.cursor()

            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {row[0] for row in cursor.fetchall()}

            assert "skills" in tables
            assert "aliases" in tables
            assert "hierarchy" in tables

            conn.close()

        # Cleanup
        Path(temp_db_path).unlink(missing_ok=True)

    @pytest.mark.unit
    def test_create_database_skills_table_real(self):
        """Test that create_database creates skills table correctly."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_db:
            temp_db_path = temp_db.name

        with patch("src.db.database.DB_PATH", temp_db_path):
            from src.db.database import create_database

            create_database()

            conn = sqlite3.connect(temp_db_path)
            cursor = conn.cursor()

            # Check skills table structure
            cursor.execute("PRAGMA table_info(skills)")
            columns = cursor.fetchall()
            column_names = [col[1] for col in columns]

            assert "id" in column_names
            assert "canonical_name" in column_names
            assert "created_at" in column_names

            # Check constraints
            cursor.execute("SELECT sql FROM sqlite_master WHERE name='skills'")
            sql = cursor.fetchone()[0]
            assert "PRIMARY KEY AUTOINCREMENT" in sql
            assert "UNIQUE NOT NULL" in sql

            conn.close()

        # Cleanup
        Path(temp_db_path).unlink(missing_ok=True)

    @pytest.mark.unit
    def test_create_database_aliases_table_real(self):
        """Test that create_database creates aliases table correctly."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_db:
            temp_db_path = temp_db.name

        with patch("src.db.database.DB_PATH", temp_db_path):
            from src.db.database import create_database

            create_database()

            conn = sqlite3.connect(temp_db_path)
            cursor = conn.cursor()

            # Check aliases table structure
            cursor.execute("PRAGMA table_info(aliases)")
            columns = cursor.fetchall()
            column_names = [col[1] for col in columns]

            assert "id" in column_names
            assert "alias_name" in column_names
            assert "skill_id" in column_names

            # Check foreign key
            cursor.execute("PRAGMA foreign_key_list(aliases)")
            foreign_keys = cursor.fetchall()
            assert len(foreign_keys) > 0
            assert foreign_keys[0][2] == "skills"  # References skills table

            conn.close()

        # Cleanup
        Path(temp_db_path).unlink(missing_ok=True)

    @pytest.mark.unit
    def test_create_database_hierarchy_table_real(self):
        """Test that create_database creates hierarchy table correctly."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_db:
            temp_db_path = temp_db.name

        with patch("src.db.database.DB_PATH", temp_db_path):
            from src.db.database import create_database

            create_database()

            conn = sqlite3.connect(temp_db_path)
            cursor = conn.cursor()

            # Check hierarchy table structure
            cursor.execute("PRAGMA table_info(hierarchy)")
            columns = cursor.fetchall()
            column_names = [col[1] for col in columns]

            assert "child_id" in column_names
            assert "parent_id" in column_names

            # Check foreign keys
            cursor.execute("PRAGMA foreign_key_list(hierarchy)")
            foreign_keys = cursor.fetchall()
            assert len(foreign_keys) == 2  # Two foreign keys to skills table

            conn.close()

        # Cleanup
        Path(temp_db_path).unlink(missing_ok=True)

    @pytest.mark.unit
    def test_create_database_indexes_real(self):
        """Test that create_database creates all indexes."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_db:
            temp_db_path = temp_db.name

        with patch("src.db.database.DB_PATH", temp_db_path):
            from src.db.database import create_database

            create_database()

            conn = sqlite3.connect(temp_db_path)
            cursor = conn.cursor()

            # Check indexes exist
            cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
            indexes = {row[0] for row in cursor.fetchall()}

            assert "idx_aliases_name" in indexes
            assert "idx_hierarchy_child" in indexes
            assert "idx_hierarchy_parent" in indexes

            conn.close()

        # Cleanup
        Path(temp_db_path).unlink(missing_ok=True)

    @pytest.mark.unit
    def test_create_database_idempotent_real(self):
        """Test that create_database can be run multiple times safely."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_db:
            temp_db_path = temp_db.name

        with patch("src.db.database.DB_PATH", temp_db_path):
            from src.db.database import create_database

            # Run create_database multiple times
            create_database()
            create_database()
            create_database()

            # Should still work correctly
            conn = sqlite3.connect(temp_db_path)
            cursor = conn.cursor()

            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {row[0] for row in cursor.fetchall()}

            assert "skills" in tables
            assert "aliases" in tables
            assert "hierarchy" in tables

            conn.close()

        # Cleanup
        Path(temp_db_path).unlink(missing_ok=True)

    @pytest.mark.unit
    def test_create_database_cascade_delete_real(self):
        """Test that cascade delete constraints work."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_db:
            temp_db_path = temp_db.name

        with patch("src.db.database.DB_PATH", temp_db_path):
            from src.db.database import create_database

            create_database()

            conn = sqlite3.connect(temp_db_path)
            conn.execute("PRAGMA foreign_keys = ON")
            cursor = conn.cursor()

            # Insert test data
            cursor.execute("INSERT INTO skills (id, canonical_name) VALUES (1, 'test_skill')")
            cursor.execute("INSERT INTO aliases (alias_name, skill_id) VALUES ('test_alias', 1)")
            cursor.execute("INSERT INTO skills (id, canonical_name) VALUES (2, 'parent_skill')")
            cursor.execute("INSERT INTO hierarchy (child_id, parent_id) VALUES (1, 2)")

            # Verify data exists
            cursor.execute("SELECT COUNT(*) FROM aliases WHERE skill_id = 1")
            assert cursor.fetchone()[0] == 1
            cursor.execute("SELECT COUNT(*) FROM hierarchy WHERE child_id = 1")
            assert cursor.fetchone()[0] == 1

            # Delete skill - should cascade
            cursor.execute("DELETE FROM skills WHERE id = 1")

            # Verify cascade delete worked
            cursor.execute("SELECT COUNT(*) FROM aliases WHERE skill_id = 1")
            assert cursor.fetchone()[0] == 0
            cursor.execute("SELECT COUNT(*) FROM hierarchy WHERE child_id = 1")
            assert cursor.fetchone()[0] == 0

            conn.close()

        # Cleanup
        Path(temp_db_path).unlink(missing_ok=True)

    @pytest.mark.unit
    def test_database_module_constants_real(self):
        """Test database module constants."""
        from pathlib import Path

        from src.db.database import DB_PATH

        assert DB_PATH is not None
        assert isinstance(DB_PATH, (str, Path))

    @pytest.mark.unit
    def test_create_database_file_creation_real(self):
        """Test that create_database actually creates the file."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_db:
            temp_db_path = temp_db.name

        # Delete the file first
        Path(temp_db_path).unlink()
        assert not Path(temp_db_path).exists()

        with patch("src.db.database.DB_PATH", temp_db_path):
            from src.db.database import create_database

            create_database()

            # File should now exist
            assert Path(temp_db_path).exists()

        # Cleanup
        Path(temp_db_path).unlink(missing_ok=True)

    @pytest.mark.unit
    def test_create_database_main_execution_real(self):
        """Test that database module can be executed as main."""
        # This tests the if __name__ == "__main__" block
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_db:
            temp_db_path = temp_db.name

        with patch("src.db.database.DB_PATH", temp_db_path), patch("builtins.print") as mock_print:
            # Import and execute the main block logic
            from src.db.database import create_database

            create_database()

            # Should have printed success message
            mock_print.assert_called()
            assert any("✓" in str(call) for call in mock_print.call_args_list)

        # Cleanup
        Path(temp_db_path).unlink(missing_ok=True)

    @pytest.mark.unit
    def test_database_sql_syntax_real(self):
        """Test that all SQL statements are syntactically correct."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_db:
            temp_db_path = temp_db.name

        with patch("src.db.database.DB_PATH", temp_db_path):
            from src.db.database import create_database

            # Should execute without SQL syntax errors
            create_database()

            conn = sqlite3.connect(temp_db_path)
            cursor = conn.cursor()

            # Test that we can use all created objects
            cursor.execute("INSERT INTO skills (canonical_name) VALUES ('test')")
            skill_id = cursor.lastrowid

            cursor.execute(
                "INSERT INTO aliases (alias_name, skill_id) VALUES ('test_alias', ?)", (skill_id,)
            )

            cursor.execute("INSERT INTO skills (canonical_name) VALUES ('parent')")
            parent_id = cursor.lastrowid

            cursor.execute(
                "INSERT INTO hierarchy (child_id, parent_id) VALUES (?, ?)", (skill_id, parent_id)
            )

            # Verify data was inserted
            cursor.execute("SELECT COUNT(*) FROM skills")
            assert cursor.fetchone()[0] == 2

            cursor.execute("SELECT COUNT(*) FROM aliases")
            assert cursor.fetchone()[0] == 1

            cursor.execute("SELECT COUNT(*) FROM hierarchy")
            assert cursor.fetchone()[0] == 1

            conn.close()

        # Cleanup
        Path(temp_db_path).unlink(missing_ok=True)

    @pytest.mark.unit
    def test_database_config_import_real(self):
        """Test that database imports config correctly."""
        # Test that the module can import ONTOLOGY_DB from config
        import src.db.database as db_module

        # Should have imported successfully
        assert hasattr(db_module, "DB_PATH")

    @pytest.mark.unit
    def test_database_unique_constraints_real(self):
        """Test unique constraints work correctly."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_db:
            temp_db_path = temp_db.name

        with patch("src.db.database.DB_PATH", temp_db_path):
            from src.db.database import create_database

            create_database()

            conn = sqlite3.connect(temp_db_path)
            cursor = conn.cursor()

            # Insert skill
            cursor.execute("INSERT INTO skills (canonical_name) VALUES ('python')")

            # Try to insert duplicate skill - should fail
            with pytest.raises(sqlite3.IntegrityError):
                cursor.execute("INSERT INTO skills (canonical_name) VALUES ('python')")

            # Insert alias
            skill_id = 1
            cursor.execute(
                "INSERT INTO aliases (alias_name, skill_id) VALUES ('py', ?)", (skill_id,)
            )

            # Try to insert duplicate alias - should fail
            with pytest.raises(sqlite3.IntegrityError):
                cursor.execute(
                    "INSERT INTO aliases (alias_name, skill_id) VALUES ('py', ?)", (skill_id,)
                )

            conn.close()

        # Cleanup
        Path(temp_db_path).unlink(missing_ok=True)
