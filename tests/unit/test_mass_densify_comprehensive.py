#!/usr/bin/env python3
"""
Comprehensive tests for mass_densify.py CLI tool.
"""

from unittest.mock import Mock, patch

import pytest


class TestMassDensifyComprehensive:
    """Comprehensive tests for mass densify functionality."""

    @pytest.mark.unit
    def test_mass_densifier_init(self):
        """Test MassDensifier initialization."""
        from src.cli.mass_densify import MassDensifier

        densifier = MassDensifier()

        assert densifier.db_path == "ontology.db"
        assert densifier.unmapped_file == "data/output/unmapped_skills_analysis.csv"
        assert densifier.log_file == "data/output/densification_log.json"
        assert "start_time" in densifier.stats
        assert densifier.stats["processed"] == 0

    @pytest.mark.unit
    def test_get_current_stats(self):
        """Test getting current stats from database."""
        from src.cli.mass_densify import MassDensifier

        densifier = MassDensifier()

        mock_conn = Mock()
        mock_cursor = Mock()
        mock_conn.cursor.return_value = mock_cursor

        # Mock the execute method to return mock_cursor itself for chaining
        mock_execute_result = Mock()
        mock_execute_result.fetchone.side_effect = [(250,), (1000,), (500,)]
        mock_cursor.execute.return_value = mock_execute_result

        with patch("sqlite3.connect", return_value=mock_conn):
            stats = densifier.get_current_stats()

        assert stats["skills"] == 250
        assert stats["aliases"] == 1000
        assert stats["hierarchy"] == 500

    @pytest.mark.unit
    def test_reload_api_cache_success(self):
        """Test successful API cache reload."""
        from src.cli.mass_densify import MassDensifier

        densifier = MassDensifier()

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"message": "Cache reloaded"}

        with patch("requests.post", return_value=mock_response):
            result = densifier.reload_api_cache()

        assert result is True

    @pytest.mark.unit
    def test_reload_api_cache_failure(self):
        """Test API cache reload failure."""
        from src.cli.mass_densify import MassDensifier

        densifier = MassDensifier()

        with patch("requests.post", side_effect=Exception("Network error")):
            result = densifier.reload_api_cache()

        assert result is False
