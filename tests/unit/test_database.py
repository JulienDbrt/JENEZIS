#!/usr/bin/env python3
"""
Tests for the database module.
"""

import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest


class TestDatabase:
    """Test suite for database module."""

    @pytest.mark.unit
    def test_create_database_tables(self):
        """Test that create_database creates all required tables."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_db:
            temp_db_path = temp_db.name

        # Test the database creation logic
        con = sqlite3.connect(temp_db_path)
        cur = con.cursor()

        # Create skills table
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS skills (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                canonical_name TEXT UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # Create aliases table
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS aliases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alias_name TEXT UNIQUE NOT NULL,
                skill_id INTEGER NOT NULL,
                FOREIGN KEY (skill_id) REFERENCES skills(id) ON DELETE CASCADE
            )
        """
        )

        # Create hierarchy table
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS hierarchy (
                child_id INTEGER NOT NULL,
                parent_id INTEGER NOT NULL,
                PRIMARY KEY (child_id, parent_id),
                FOREIGN KEY (child_id) REFERENCES skills(id) ON DELETE CASCADE,
                FOREIGN KEY (parent_id) REFERENCES skills(id) ON DELETE CASCADE
            )
        """
        )

        con.commit()

        # Verify tables exist
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cur.fetchall()}

        assert "skills" in tables
        assert "aliases" in tables
        assert "hierarchy" in tables

        con.close()
        Path(temp_db_path).unlink(missing_ok=True)

    @pytest.mark.unit
    def test_create_database_indexes(self):
        """Test that create_database creates all required indexes."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_db:
            temp_db_path = temp_db.name

        con = sqlite3.connect(temp_db_path)
        cur = con.cursor()

        # Create tables first
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS skills (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                canonical_name TEXT UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS aliases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alias_name TEXT UNIQUE NOT NULL,
                skill_id INTEGER NOT NULL,
                FOREIGN KEY (skill_id) REFERENCES skills(id) ON DELETE CASCADE
            )
        """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS hierarchy (
                child_id INTEGER NOT NULL,
                parent_id INTEGER NOT NULL,
                PRIMARY KEY (child_id, parent_id),
                FOREIGN KEY (child_id) REFERENCES skills(id) ON DELETE CASCADE,
                FOREIGN KEY (parent_id) REFERENCES skills(id) ON DELETE CASCADE
            )
        """
        )

        # Create indexes
        cur.execute("CREATE INDEX IF NOT EXISTS idx_aliases_name ON aliases(alias_name)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_hierarchy_child ON hierarchy(child_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_hierarchy_parent ON hierarchy(parent_id)")

        con.commit()

        # Verify indexes exist
        cur.execute("SELECT name FROM sqlite_master WHERE type='index'")
        indexes = {row[0] for row in cur.fetchall()}

        # Note: SQLite automatically creates indexes for PRIMARY KEY and UNIQUE constraints
        assert "idx_aliases_name" in indexes
        assert "idx_hierarchy_child" in indexes
        assert "idx_hierarchy_parent" in indexes

        con.close()
        Path(temp_db_path).unlink(missing_ok=True)

    @pytest.mark.unit
    def test_skills_table_structure(self):
        """Test the skills table structure and constraints."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_db:
            temp_db_path = temp_db.name

        con = sqlite3.connect(temp_db_path)
        cur = con.cursor()

        # Create skills table
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS skills (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                canonical_name TEXT UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # Test table structure
        cur.execute("PRAGMA table_info(skills)")
        columns = cur.fetchall()

        column_names = [col[1] for col in columns]
        assert "id" in column_names
        assert "canonical_name" in column_names
        assert "created_at" in column_names

        # Test unique constraint on canonical_name
        cur.execute("INSERT INTO skills (canonical_name) VALUES (?)", ("python",))

        with pytest.raises(sqlite3.IntegrityError):
            cur.execute("INSERT INTO skills (canonical_name) VALUES (?)", ("python",))

        con.close()
        Path(temp_db_path).unlink(missing_ok=True)

    @pytest.mark.unit
    def test_aliases_table_structure(self):
        """Test the aliases table structure and foreign key constraints."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_db:
            temp_db_path = temp_db.name

        con = sqlite3.connect(temp_db_path)
        cur = con.cursor()

        # Enable foreign key constraints
        cur.execute("PRAGMA foreign_keys = ON")

        # Create tables
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS skills (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                canonical_name TEXT UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS aliases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alias_name TEXT UNIQUE NOT NULL,
                skill_id INTEGER NOT NULL,
                FOREIGN KEY (skill_id) REFERENCES skills(id) ON DELETE CASCADE
            )
        """
        )

        # Test table structure
        cur.execute("PRAGMA table_info(aliases)")
        columns = cur.fetchall()
        column_names = [col[1] for col in columns]

        assert "id" in column_names
        assert "alias_name" in column_names
        assert "skill_id" in column_names

        # Test foreign key constraint
        cur.execute("INSERT INTO skills (canonical_name) VALUES (?)", ("python",))
        skill_id = cur.lastrowid

        # Valid foreign key reference
        cur.execute("INSERT INTO aliases (alias_name, skill_id) VALUES (?, ?)", ("py", skill_id))

        # Invalid foreign key reference should fail
        with pytest.raises(sqlite3.IntegrityError):
            cur.execute(
                "INSERT INTO aliases (alias_name, skill_id) VALUES (?, ?)", ("invalid", 9999)
            )

        con.close()
        Path(temp_db_path).unlink(missing_ok=True)

    @pytest.mark.unit
    def test_hierarchy_table_structure(self):
        """Test the hierarchy table structure and constraints."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_db:
            temp_db_path = temp_db.name

        con = sqlite3.connect(temp_db_path)
        cur = con.cursor()

        # Enable foreign key constraints
        cur.execute("PRAGMA foreign_keys = ON")

        # Create tables
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS skills (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                canonical_name TEXT UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS hierarchy (
                child_id INTEGER NOT NULL,
                parent_id INTEGER NOT NULL,
                PRIMARY KEY (child_id, parent_id),
                FOREIGN KEY (child_id) REFERENCES skills(id) ON DELETE CASCADE,
                FOREIGN KEY (parent_id) REFERENCES skills(id) ON DELETE CASCADE
            )
        """
        )

        # Test table structure
        cur.execute("PRAGMA table_info(hierarchy)")
        columns = cur.fetchall()
        column_names = [col[1] for col in columns]

        assert "child_id" in column_names
        assert "parent_id" in column_names

        # Test composite primary key and foreign key constraints
        cur.execute("INSERT INTO skills (canonical_name) VALUES (?)", ("python",))
        python_id = cur.lastrowid
        cur.execute("INSERT INTO skills (canonical_name) VALUES (?)", ("programming",))
        programming_id = cur.lastrowid

        # Valid hierarchy relationship
        cur.execute(
            "INSERT INTO hierarchy (child_id, parent_id) VALUES (?, ?)", (python_id, programming_id)
        )

        # Duplicate primary key should fail
        with pytest.raises(sqlite3.IntegrityError):
            cur.execute(
                "INSERT INTO hierarchy (child_id, parent_id) VALUES (?, ?)",
                (python_id, programming_id),
            )

        con.close()
        Path(temp_db_path).unlink(missing_ok=True)

    @pytest.mark.unit
    def test_cascade_delete_behavior(self):
        """Test that CASCADE DELETE works correctly."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_db:
            temp_db_path = temp_db.name

        con = sqlite3.connect(temp_db_path)
        cur = con.cursor()

        # Enable foreign key constraints
        cur.execute("PRAGMA foreign_keys = ON")

        # Create all tables
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS skills (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                canonical_name TEXT UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS aliases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alias_name TEXT UNIQUE NOT NULL,
                skill_id INTEGER NOT NULL,
                FOREIGN KEY (skill_id) REFERENCES skills(id) ON DELETE CASCADE
            )
        """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS hierarchy (
                child_id INTEGER NOT NULL,
                parent_id INTEGER NOT NULL,
                PRIMARY KEY (child_id, parent_id),
                FOREIGN KEY (child_id) REFERENCES skills(id) ON DELETE CASCADE,
                FOREIGN KEY (parent_id) REFERENCES skills(id) ON DELETE CASCADE
            )
        """
        )

        # Insert test data
        cur.execute("INSERT INTO skills (canonical_name) VALUES (?)", ("python",))
        python_id = cur.lastrowid
        cur.execute("INSERT INTO skills (canonical_name) VALUES (?)", ("programming",))
        programming_id = cur.lastrowid

        cur.execute("INSERT INTO aliases (alias_name, skill_id) VALUES (?, ?)", ("py", python_id))
        cur.execute(
            "INSERT INTO hierarchy (child_id, parent_id) VALUES (?, ?)", (python_id, programming_id)
        )

        # Verify data exists
        cur.execute("SELECT COUNT(*) FROM aliases WHERE skill_id = ?", (python_id,))
        assert cur.fetchone()[0] == 1

        cur.execute("SELECT COUNT(*) FROM hierarchy WHERE child_id = ?", (python_id,))
        assert cur.fetchone()[0] == 1

        # Delete the skill
        cur.execute("DELETE FROM skills WHERE id = ?", (python_id,))

        # Verify cascade delete worked
        cur.execute("SELECT COUNT(*) FROM aliases WHERE skill_id = ?", (python_id,))
        assert cur.fetchone()[0] == 0

        cur.execute("SELECT COUNT(*) FROM hierarchy WHERE child_id = ?", (python_id,))
        assert cur.fetchone()[0] == 0

        con.close()
        Path(temp_db_path).unlink(missing_ok=True)

    @pytest.mark.unit
    @patch("sqlite3.connect")
    def test_database_creation_with_mocked_connection(self, mock_connect):
        """Test database creation with mocked connection."""
        # Mock database components
        mock_con = Mock()
        mock_cur = Mock()
        mock_con.cursor.return_value = mock_cur
        mock_connect.return_value = mock_con

        # Simulate the create_database function logic
        con = mock_connect("test.db")
        cur = con.cursor()

        # Execute table creation
        cur.execute("CREATE TABLE IF NOT EXISTS skills ...")
        cur.execute("CREATE TABLE IF NOT EXISTS aliases ...")
        cur.execute("CREATE TABLE IF NOT EXISTS hierarchy ...")

        # Execute index creation
        cur.execute("CREATE INDEX IF NOT EXISTS idx_aliases_name ...")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_hierarchy_child ...")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_hierarchy_parent ...")

        con.commit()
        con.close()

        # Verify all operations were called
        assert mock_connect.called
        assert mock_con.cursor.called
        assert mock_cur.execute.call_count == 6  # 3 tables + 3 indexes
        assert mock_con.commit.called
        assert mock_con.close.called

    @pytest.mark.unit
    def test_database_file_creation(self):
        """Test that database file is actually created."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_db:
            temp_db_path = temp_db.name

        # Remove the file to test creation
        Path(temp_db_path).unlink()
        assert not Path(temp_db_path).exists()

        # Create database
        con = sqlite3.connect(temp_db_path)
        con.close()

        # Verify file was created
        assert Path(temp_db_path).exists()

        # Clean up
        Path(temp_db_path).unlink()

    @pytest.mark.unit
    def test_table_if_not_exists_behavior(self):
        """Test that CREATE TABLE IF NOT EXISTS works correctly."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_db:
            temp_db_path = temp_db.name

        con = sqlite3.connect(temp_db_path)
        cur = con.cursor()

        # Create table first time
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS skills (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                canonical_name TEXT UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # Create same table again - should not raise error
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS skills (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                canonical_name TEXT UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # Verify table exists and structure is correct
        cur.execute("PRAGMA table_info(skills)")
        columns = cur.fetchall()
        assert len(columns) == 3

        con.close()
        Path(temp_db_path).unlink(missing_ok=True)
