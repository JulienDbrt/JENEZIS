#!/usr/bin/env python3
"""
Simple tests for import_approved.py CLI tool.
"""

from unittest.mock import Mock, patch

import pandas as pd
import pytest


class TestImportApprovedSimple:
    """Simple tests for import_approved."""

    @pytest.mark.unit
    def test_import_function_exists(self):
        """Test that main function exists."""
        from src.cli.import_approved import import_approved_skills

        assert callable(import_approved_skills)

    @pytest.mark.unit
    def test_import_with_mock_data(self):
        """Test importing with mock data."""
        from src.cli.import_approved import import_approved_skills

        sample_df = pd.DataFrame(
            {
                "skill": ["test"],
                "canonical_name": ["test"],
                "aliases": ["t"],
                "parents": ["cat"],
                "approve": ["OUI"],
            }
        )

        mock_conn = Mock()
        mock_cursor = Mock()
        mock_cursor.lastrowid = 1
        mock_cursor.fetchone.return_value = (0,)
        mock_conn.cursor.return_value = mock_cursor

        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("pandas.read_csv", return_value=sample_df),
            patch("sqlite3.connect", return_value=mock_conn),
        ):
            result = import_approved_skills("test.csv")

        assert result is True

    @pytest.mark.unit
    def test_import_no_file(self):
        """Test when no file exists."""
        from src.cli.import_approved import import_approved_skills

        with patch("pathlib.Path.exists", return_value=False):
            result = import_approved_skills()

        assert result is False

    @pytest.mark.unit
    def test_main_callable(self):
        """Test main function is callable."""
        from src.cli.import_approved import main

        assert callable(main)
