#!/usr/bin/env python3
"""
Tests for PostgreSQL connection management module.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock


class TestPostgresConnection:
    """Tests for PostgreSQL connection utilities in src/db/postgres_connection.py."""

    @pytest.mark.unit
    def test_database_url_from_env(self):
        """Test that DATABASE_URL is read from environment."""
        from src.db.postgres_connection import DATABASE_URL

        assert DATABASE_URL is not None
        assert "postgresql" in DATABASE_URL

    @pytest.mark.unit
    def test_engine_exists(self):
        """Test that SQLAlchemy engine is created."""
        from src.db.postgres_connection import engine

        assert engine is not None
        assert engine.url is not None

    @pytest.mark.unit
    def test_session_local_factory(self):
        """Test that SessionLocal factory is created."""
        from src.db.postgres_connection import SessionLocal

        assert SessionLocal is not None
        assert callable(SessionLocal)

    @pytest.mark.unit
    def test_get_db_context_manager_exists(self):
        """Test that get_db context manager exists."""
        from src.db.postgres_connection import get_db

        assert callable(get_db)

    @pytest.mark.unit
    def test_init_db_function_exists(self):
        """Test that init_db function exists."""
        from src.db.postgres_connection import init_db

        assert callable(init_db)

    @pytest.mark.unit
    def test_drop_db_function_exists(self):
        """Test that drop_db function exists."""
        from src.db.postgres_connection import drop_db

        assert callable(drop_db)

    @pytest.mark.unit
    def test_async_database_url(self):
        """Test that async database URL is correctly transformed."""
        from src.db.postgres_connection import ASYNC_DATABASE_URL

        assert "asyncpg" in ASYNC_DATABASE_URL

    @pytest.mark.unit
    def test_async_engine_exists(self):
        """Test that async engine is created."""
        from src.db.postgres_connection import async_engine

        assert async_engine is not None

    @pytest.mark.unit
    def test_async_session_local_exists(self):
        """Test that AsyncSessionLocal factory is created."""
        from src.db.postgres_connection import AsyncSessionLocal

        assert AsyncSessionLocal is not None

    @pytest.mark.unit
    def test_get_async_db_function_exists(self):
        """Test that get_async_db function exists."""
        from src.db.postgres_connection import get_async_db

        assert callable(get_async_db)

    @pytest.mark.unit
    def test_set_postgres_pragmas_function_exists(self):
        """Test that set_postgres_pragmas function exists."""
        from src.db.postgres_connection import set_postgres_pragmas

        assert callable(set_postgres_pragmas)

    @pytest.mark.unit
    def test_set_postgres_pragmas_executes_commands(self):
        """Test that set_postgres_pragmas executes the expected SQL commands."""
        from src.db.postgres_connection import set_postgres_pragmas

        mock_connection = Mock()
        mock_cursor = Mock()
        mock_connection.cursor.return_value = mock_cursor

        set_postgres_pragmas(mock_connection, None)

        # Verify cursor was created and used
        mock_connection.cursor.assert_called_once()
        assert mock_cursor.execute.call_count == 2
        mock_cursor.close.assert_called_once()

        # Verify the SQL commands
        calls = [str(call) for call in mock_cursor.execute.call_args_list]
        assert any("statement_timeout" in str(call) for call in calls)
        assert any("timezone" in str(call) for call in calls)

    @pytest.mark.unit
    def test_pool_configuration(self):
        """Test that engine is configured with proper pool settings."""
        from src.db.postgres_connection import engine

        # Check pool configuration
        pool = engine.pool
        assert pool is not None
